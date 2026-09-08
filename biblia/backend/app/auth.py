"""Accounts, password hashing and JWT sessions.

Password hashing uses `hashlib.scrypt` from the standard library — a memory-hard
KDF that is a genuinely appropriate choice here, and one fewer native dependency
to install and keep patched than bcrypt or argon2 bindings.

Authentication is *optional everywhere*. Reading, searching, comparing
translations and asking questions all work signed out; an account only adds the
personal layer. So the dependency used by most routes is `current_user_optional`,
which returns None rather than raising, and only the endpoints that touch
personal data require a real user.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request

from . import config

# scrypt parameters. n=2**15 costs ~50ms and 32MB per verification, which is
# the right order of magnitude for a login: slow enough to make offline
# cracking expensive, fast enough not to be a denial-of-service vector.
#
# maxmem must be set explicitly: these parameters need 128*N*r = exactly 32MiB,
# and OpenSSL's default cap is also 32MiB, so the call fails by a hair without
# it. Raising the ceiling to 64MiB does not change the work actually done.
_N, _R, _P, _DKLEN = 2**15, 8, 1, 32
_MAXMEM = 64 * 1024 * 1024


def _scrypt(password: bytes, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(password, salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=_MAXMEM)

_JWT_ALG = "HS256"
_TOKEN_DAYS = 30

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _secret() -> str:
    return config.settings.secret_key


# ---------------------------------------------------------------------------
# passwords
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = _scrypt(password.encode(), salt, _N, _R, _P, _DKLEN)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = _scrypt(
            password.encode(), base64.b64decode(salt_b64),
            int(n), int(r), int(p), len(base64.b64decode(dk_b64)),
        )
    except (ValueError, TypeError):
        return False
    # constant-time comparison so verification time cannot leak the hash
    return hmac.compare_digest(dk, base64.b64decode(dk_b64))


def password_problem(password: str) -> str | None:
    if len(password) < 10:
        return "Password must be at least 10 characters."
    if len(password) > 200:
        return "Password must be under 200 characters."
    return None


# ---------------------------------------------------------------------------
# tokens
# ---------------------------------------------------------------------------


def make_token(user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "email": email, "iat": now,
         "exp": now + timedelta(days=_TOKEN_DAYS)},
        _secret(), algorithm=_JWT_ALG,
    )


def read_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _secret(), algorithms=[_JWT_ALG])
    except jwt.PyJWTError:
        return None


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


# ---------------------------------------------------------------------------
# user records
# ---------------------------------------------------------------------------


def create_user(conn: sqlite3.Connection, email: str, password: str, display_name: str) -> dict:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "That does not look like a valid email address.")
    if problem := password_problem(password):
        raise HTTPException(400, problem)

    exists = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
    if exists:
        raise HTTPException(409, "An account with that email already exists.")

    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, display_name, created_at) VALUES (?,?,?,?)",
        (email, hash_password(password), (display_name or email.split("@")[0]).strip()[:80], now),
    )
    uid = cur.lastrowid
    conn.execute("INSERT INTO user_settings (user_id) VALUES (?)", (uid,))
    conn.commit()
    return get_user(conn, uid)


def authenticate(conn: sqlite3.Connection, email: str, password: str) -> dict:
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
    ).fetchone()
    # Verify against a dummy hash when the account is absent, so that a missing
    # account and a wrong password take the same time and cannot be told apart.
    if not row:
        _scrypt(b"x", b"y" * 16, _N, _R, _P, _DKLEN)
        raise HTTPException(401, "Incorrect email or password.")
    if not verify_password(password, row["password_hash"]):
        raise HTTPException(401, "Incorrect email or password.")
    return get_user(conn, row["id"])


def get_user(conn: sqlite3.Connection, user_id: int) -> dict:
    row = conn.execute(
        "SELECT id, email, display_name, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "User not found.")
    s = conn.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    if not s:
        conn.execute("INSERT INTO user_settings (user_id) VALUES (?)", (user_id,))
        conn.commit()
        s = conn.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    return {**dict(row), "settings": {k: s[k] for k in s.keys() if k != "user_id"}}


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


def current_user_optional(request: Request) -> dict | None:
    """Resolve the caller if a valid token is present; otherwise None.

    This is the default for content routes so that everything readable stays
    readable while signed out.
    """
    token = _bearer(request)
    if not token:
        return None
    claims = read_token(token)
    if not claims:
        return None
    from .main import db  # imported here to avoid a circular import at module load

    try:
        return get_user(db(), int(claims["sub"]))
    except (HTTPException, KeyError, ValueError):
        return None


def current_user(user: dict | None = Depends(current_user_optional)) -> dict:
    """Require a signed-in caller. Used only by routes touching personal data."""
    if not user:
        raise HTTPException(401, "Sign in to use this.")
    return user
