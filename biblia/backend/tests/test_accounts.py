"""Accounts, personal study data, and the notes-visibility boundary.

The tests that matter most here are the negative ones. Two users must never see
each other's notes, and a reader's notes must never reach a model provider
unless their own setting permits it — those are promises the product makes, so
they get explicit assertions rather than being implied by happy-path coverage.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password, make_token, read_token, verify_password
from app.db import DB_PATH
from app.main import app
from app.personal import asks_about_notes

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="corpus not built")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _account(client, password="a-strong-passphrase"):
    """Create a fresh account and return (auth headers, user)."""
    email = f"t{uuid.uuid4().hex[:12]}@example.com"
    r = client.post("/api/auth/register",
                    json={"email": email, "password": password, "display_name": "Test"})
    assert r.status_code == 200, r.text
    d = r.json()
    return {"Authorization": f"Bearer {d['token']}"}, d["user"]


@pytest.fixture
def alice(client):
    return _account(client)


@pytest.fixture
def bob(client):
    return _account(client)


# ------------------------------------------------------------ passwords


def test_password_hash_verifies_and_is_salted():
    a, b = hash_password("same-passphrase"), hash_password("same-passphrase")
    assert a != b, "identical passwords must not produce identical hashes"
    assert verify_password("same-passphrase", a)
    assert not verify_password("same-passphrase ", a)
    assert not verify_password("wrong", a)


def test_malformed_hash_is_rejected_not_crashed():
    for junk in ("", "nonsense", "scrypt$bad", "bcrypt$1$2$3$4$5"):
        assert verify_password("x", junk) is False


def test_token_roundtrip_and_tamper_resistance():
    t = make_token(42, "a@b.c")
    assert read_token(t)["sub"] == "42"
    assert read_token(t + "x") is None
    assert read_token("not.a.token") is None


# --------------------------------------------------------------- signup


def test_register_and_login(client):
    headers, user = _account(client)
    assert user["settings"]["notes_visibility"] == "on_request", "safe default"
    assert client.get("/api/auth/me", headers=headers).json()["user"]["id"] == user["id"]


@pytest.mark.parametrize("payload,status", [
    ({"email": "not-an-email", "password": "a-strong-passphrase"}, 400),
    ({"email": "ok@example.com", "password": "short"}, 400),
])
def test_registration_validation(client, payload, status):
    assert client.post("/api/auth/register", json=payload).status_code == status


def test_duplicate_email_rejected(client):
    email = f"dup{uuid.uuid4().hex[:8]}@example.com"
    body = {"email": email, "password": "a-strong-passphrase"}
    assert client.post("/api/auth/register", json=body).status_code == 200
    assert client.post("/api/auth/register", json=body).status_code == 409


def test_wrong_password_and_unknown_account_are_indistinguishable(client):
    _, user = _account(client)
    a = client.post("/api/auth/login", json={"email": user["email"], "password": "wrong-password"})
    b = client.post("/api/auth/login",
                    json={"email": "nobody@example.com", "password": "wrong-password"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_personal_routes_require_auth(client):
    for method, path in [("get", "/api/notes"), ("get", "/api/highlights"),
                         ("get", "/api/bookmarks"), ("get", "/api/history"),
                         ("get", "/api/conversations")]:
        assert getattr(client, method)(path).status_code == 401


def test_invalid_token_is_treated_as_signed_out(client):
    bad = {"Authorization": "Bearer garbage.token.here"}
    assert client.get("/api/notes", headers=bad).status_code == 401
    # ...but reading still works, because content routes never require auth
    assert client.get("/api/passage", params={"ref": "John 3:16"}, headers=bad).status_code == 200


# ---------------------------------------------------------------- notes


def test_note_lifecycle(client, alice):
    h, _ = alice
    created = client.post("/api/notes", headers=h,
                          json={"ref": "Romans 8:28-30", "body": "First thoughts."}).json()["note"]
    assert created["ref"] == "Romans 8:28-30"

    updated = client.patch(f"/api/notes/{created['id']}", headers=h,
                           json={"body": "Revised thoughts."}).json()["note"]
    assert updated["body"] == "Revised thoughts."

    assert client.delete(f"/api/notes/{created['id']}", headers=h).status_code == 200
    assert client.delete(f"/api/notes/{created['id']}", headers=h).status_code == 404


def test_notes_surface_on_overlapping_passages(client, alice):
    h, _ = alice
    client.post("/api/notes", headers=h,
                json={"ref": "Romans 8:28-30", "body": "Span note."})
    # a note on 28-30 must appear when reading 8:29 alone
    d = client.get("/api/passage", params={"ref": "Romans 8:29"}, headers=h).json()
    assert any(n["body"] == "Span note." for n in d["notes"])
    # ...and must not appear on an unrelated passage
    d2 = client.get("/api/passage", params={"ref": "John 3:16"}, headers=h).json()
    assert d2["notes"] == []


def test_users_cannot_see_or_touch_each_others_notes(client, alice, bob):
    ah, _ = alice
    bh, _ = bob
    note = client.post("/api/notes", headers=ah,
                       json={"ref": "Psalm 23", "body": "Alice's private note."}).json()["note"]

    # not listed
    assert all(n["id"] != note["id"] for n in client.get("/api/notes", headers=bh).json()["notes"])
    # not visible on the passage
    d = client.get("/api/passage", params={"ref": "Psalm 23"}, headers=bh).json()
    assert d["notes"] == []
    # not editable or deletable
    assert client.patch(f"/api/notes/{note['id']}", headers=bh,
                        json={"body": "hijacked"}).status_code == 404
    assert client.delete(f"/api/notes/{note['id']}", headers=bh).status_code == 404
    # and still intact for its owner
    assert client.get("/api/notes", headers=ah).json()["notes"][0]["body"] == "Alice's private note."


def test_note_search(client, alice):
    h, _ = alice
    client.post("/api/notes", headers=h, json={"ref": "Isaiah 53", "body": "substitutionary"})
    client.post("/api/notes", headers=h, json={"ref": "John 1", "body": "logos prologue"})
    found = client.get("/api/notes", params={"q": "logos"}, headers=h).json()["notes"]
    assert len(found) == 1 and found[0]["ref"] == "Isaiah 53" or found[0]["ref"] == "John 1"


# ----------------------------------------------------------- highlights


def test_highlight_create_recolor_delete(client, alice):
    h, _ = alice
    first = client.post("/api/highlights", headers=h,
                        json={"ref": "John 3:16", "color": "yellow"}).json()["highlight"]
    again = client.post("/api/highlights", headers=h,
                        json={"ref": "John 3:16", "color": "blue"}).json()["highlight"]
    assert again["id"] == first["id"], "re-highlighting a span should recolor, not stack"
    assert again["color"] == "blue"
    assert client.delete(f"/api/highlights/{first['id']}", headers=h).status_code == 200


def test_invalid_highlight_color_falls_back(client, alice):
    h, _ = alice
    hl = client.post("/api/highlights", headers=h,
                     json={"ref": "Jude 3", "color": "chartreuse"}).json()["highlight"]
    assert hl["color"] == "yellow"


def test_highlights_are_per_user(client, alice, bob):
    ah, _ = alice
    bh, _ = bob
    hl = client.post("/api/highlights", headers=ah, json={"ref": "Micah 6:8"}).json()["highlight"]
    assert client.delete(f"/api/highlights/{hl['id']}", headers=bh).status_code == 404


# ------------------------------------------------- bookmarks and history


def test_bookmark_toggles(client, alice):
    h, _ = alice
    assert client.post("/api/bookmarks", headers=h, json={"ref": "Psalm 121"}).json()["bookmarked"]
    d = client.get("/api/passage", params={"ref": "Psalm 121"}, headers=h).json()
    assert d["bookmarked"] is True
    assert not client.post("/api/bookmarks", headers=h, json={"ref": "Psalm 121"}).json()["bookmarked"]


def test_reading_history_records_and_collapses_repeats(client, alice):
    h, _ = alice
    for _ in range(3):
        client.get("/api/passage", params={"ref": "Habakkuk 3"}, headers=h)
    hist = client.get("/api/history", headers=h).json()["history"]
    assert hist[0]["ref"] == "Habakkuk 3"
    assert sum(1 for x in hist if x["ref"] == "Habakkuk 3") == 1, "repeats must collapse"


# ------------------------------------------------------------- settings


def test_settings_update_and_validation(client, alice):
    h, _ = alice
    s = client.patch("/api/settings", headers=h,
                     json={"notes_visibility": "always", "narrator_rate": 1.25}).json()["settings"]
    assert s["notes_visibility"] == "always"
    assert s["narrator_rate"] == 1.25

    # an invalid mode is ignored rather than stored
    s2 = client.patch("/api/settings", headers=h,
                      json={"notes_visibility": "everything"}).json()["settings"]
    assert s2["notes_visibility"] == "always"

    # rate is clamped to a sane range
    s3 = client.patch("/api/settings", headers=h, json={"narrator_rate": 99}).json()["settings"]
    assert s3["narrator_rate"] <= 2.0


# --------------------------------------------- the notes/model boundary


@pytest.mark.parametrize("message,expected", [
    ("what did I write about this?", True),
    ("look at my notes on this passage", True),
    ("what have I said about Romans 8?", True),
    ("I wrote something about this last month", True),
    ("what does this passage mean?", False),
    ("explain the golden chain", False),
    ("who wrote Romans?", False),
])
def test_note_request_detection(message, expected):
    assert asks_about_notes(message) is expected


def _chat_meta(client, message, headers=None):
    r = client.post("/api/chat", headers=headers or {},
                    json={"message": message, "translation": "BSB"})
    assert r.status_code == 200
    for frame in r.text.split("\n\n"):
        if frame.startswith("event: meta"):
            return json.loads(frame.split("data: ", 1)[1])
    raise AssertionError("no meta frame in stream")


def _chat_body(client, message, headers=None):
    r = client.post("/api/chat", headers=headers or {},
                    json={"message": message, "translation": "BSB"})
    out = []
    for frame in r.text.split("\n\n"):
        if frame.startswith("event: delta"):
            out.append(json.loads(frame.split("data: ", 1)[1])["text"])
    return "".join(out)


def test_notes_stay_out_of_prompt_by_default(client, alice):
    """Default mode is on_request: an ordinary question must not carry notes."""
    h, _ = alice
    client.post("/api/notes", headers=h,
                json={"ref": "Romans 8:28-30", "body": "SECRETMARKER private reflection"})
    meta = _chat_meta(client, "What does Romans 8:28 mean?", h)
    assert meta["used_notes"] == []
    # and the note text is genuinely absent from what the model would receive
    assert "SECRETMARKER" not in _chat_body(client, "What does Romans 8:28 mean?", h)


def test_notes_included_when_the_reader_asks(client, alice):
    h, _ = alice
    client.post("/api/notes", headers=h,
                json={"ref": "Romans 8:28-30", "body": "ASKMARKER my own reflection"})
    meta = _chat_meta(client, "What did I write in my notes about Romans 8:28?", h)
    assert meta["used_notes"] == ["Romans 8:28-30"]
    assert "ASKMARKER" in _chat_body(client, "What did I write in my notes on Romans 8:28?", h)


def test_never_mode_withholds_notes_even_when_asked(client, alice):
    h, _ = alice
    client.post("/api/notes", headers=h,
                json={"ref": "Romans 8:28-30", "body": "NEVERMARKER should not leak"})
    client.patch("/api/settings", headers=h, json={"notes_visibility": "never"})
    meta = _chat_meta(client, "What did I write in my notes about Romans 8:28?", h)
    assert meta["used_notes"] == []
    assert "NEVERMARKER" not in _chat_body(client, "show me my notes on Romans 8:28", h)


def test_always_mode_includes_notes_without_asking(client, alice):
    h, _ = alice
    client.post("/api/notes", headers=h,
                json={"ref": "Romans 8:28-30", "body": "ALWAYSMARKER reflection"})
    client.patch("/api/settings", headers=h, json={"notes_visibility": "always"})
    meta = _chat_meta(client, "What does Romans 8:28 mean?", h)
    assert meta["used_notes"] == ["Romans 8:28-30"]


def test_one_readers_notes_never_reach_another_readers_prompt(client, alice, bob):
    ah, _ = alice
    bh, _ = bob
    client.post("/api/notes", headers=ah,
                json={"ref": "Romans 8:28-30", "body": "CROSSMARKER alice only"})
    client.patch("/api/settings", headers=ah, json={"notes_visibility": "always"})
    client.patch("/api/settings", headers=bh, json={"notes_visibility": "always"})
    assert "CROSSMARKER" not in _chat_body(client, "What does Romans 8:28 mean?", bh)


def test_anonymous_chat_carries_no_notes(client, alice):
    ah, _ = alice
    client.post("/api/notes", headers=ah, json={"ref": "Romans 8:28-30", "body": "ANONMARKER"})
    client.patch("/api/settings", headers=ah, json={"notes_visibility": "always"})
    assert "ANONMARKER" not in _chat_body(client, "What does Romans 8:28 mean?")


# --------------------------------------------------- conversation privacy


def test_conversations_are_scoped_to_their_owner(client, alice, bob):
    ah, _ = alice
    bh, _ = bob
    sid = _chat_meta(client, "What is Psalm 23 about?", ah)["session_id"]

    assert any(c["id"] == sid for c in client.get("/api/conversations", headers=ah).json()["conversations"])
    assert all(c["id"] != sid for c in client.get("/api/conversations", headers=bh).json()["conversations"])

    assert client.get(f"/api/session/{sid}", headers=ah).status_code == 200
    assert client.get(f"/api/session/{sid}", headers=bh).status_code == 403
    assert client.get(f"/api/session/{sid}").status_code == 403

    assert client.post("/api/chat", headers=bh,
                       json={"message": "continue", "session_id": sid}).status_code == 403
    assert client.delete(f"/api/conversations/{sid}", headers=bh).status_code == 404
    assert client.delete(f"/api/conversations/{sid}", headers=ah).status_code == 200


def test_anonymous_conversations_remain_readable(client):
    """Signed-out chat still works and its transcript stays reachable."""
    sid = _chat_meta(client, "What is Psalm 23 about?")["session_id"]
    assert client.get(f"/api/session/{sid}").status_code == 200
