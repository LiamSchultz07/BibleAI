"""Biblia — FastAPI application.

Endpoints
---------
GET  /api/health                      service + corpus status
GET  /api/translations                available translations with metadata
GET  /api/books                       canon metadata
GET  /api/passage?ref=&translation=   read a passage (optionally compare)
GET  /api/chapter/{book}/{chapter}    read a whole chapter
GET  /api/search?q=                   hybrid search
GET  /api/contested?ref=              interpretive disputes for a passage
POST /api/chat                        streaming conversation over a passage
GET  /api/session/{id}                conversation history
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import uuid
from datetime import datetime, timezone

from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from . import personal as P
from .auth import authenticate, create_user, current_user, current_user_optional, get_user, make_token
from .canon import BOOKS, BY_OSIS, GENRES
from .db import DB_PATH, connect, init, range_str, unvid
from .llm.prompts import SYSTEM, anchor_summary, build_context
from .llm.provider import get_provider
from .retrieval import search as R
from .retrieval.refparse import parse_refs

app = FastAPI(title="Biblia", version="0.1.0",
              description="Conversational study over open-license Bible translations")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in config.settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_conn: sqlite3.Connection | None = None


def db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        if not DB_PATH.exists():
            raise HTTPException(
                503,
                "Corpus not built. Run: python -m app.ingest.run --source-dir <dir>",
            )
        _conn = connect()
        init(_conn)
    return _conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None
    translation: str = "BSB"
    compare: list[str] = Field(default_factory=list, max_length=5)
    anchor_ref: str | None = None


class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=200)
    display_name: str = Field("", max_length=80)


class LoginRequest(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=200)


class NoteRequest(BaseModel):
    ref: str = Field(..., max_length=120)
    body: str = Field(..., min_length=1, max_length=20_000)


class NoteUpdate(BaseModel):
    body: str = Field(..., min_length=1, max_length=20_000)


class HighlightRequest(BaseModel):
    ref: str = Field(..., max_length=120)
    color: str = Field("yellow", max_length=16)


class BookmarkRequest(BaseModel):
    ref: str = Field(..., max_length=120)
    label: str | None = Field(None, max_length=120)


class HistoryRequest(BaseModel):
    ref: str = Field(..., max_length=120)
    translation: str = Field("BSB", max_length=16)


class SettingsRequest(BaseModel):
    notes_visibility: str | None = None
    default_translation: str | None = None
    narrator_voice: str | None = None
    narrator_rate: float | None = None
    narrator_pitch: float | None = None


# ---------------------------------------------------------------------------
# corpus endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health():
    try:
        conn = db()
        counts = {
            "translations": conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0],
            "verses": conn.execute("SELECT COUNT(*) FROM verses").fetchone()[0],
            "pericopes": conn.execute("SELECT COUNT(*) FROM pericopes").fetchone()[0],
            "cross_refs": conn.execute("SELECT COUNT(*) FROM cross_refs").fetchone()[0],
            "contested": conn.execute("SELECT COUNT(*) FROM contested").fetchone()[0],
        }
        meta = conn.execute("SELECT provider, model, dim FROM embedding_meta WHERE id=1").fetchone()
        embed = dict(meta) if meta else None
    except HTTPException:
        counts, embed = {}, None
    return {
        "ok": True,
        "corpus": counts,
        "embeddings": embed,
        "llm": {
            "configured": config.settings.has_llm,
            "provider": get_provider().name,
        },
    }


@app.get("/api/translations")
def list_translations(conn: sqlite3.Connection = Depends(db)):
    return {"translations": R.translations(conn)}


@app.get("/api/books")
def list_books():
    return {
        "books": [
            {"osis": b.osis, "name": b.name, "testament": b.testament,
             "order": b.order, "genre": b.genre, "chapters": b.chapters}
            for b in BOOKS
        ],
        "genres": GENRES,
    }


def _resolve(ref: str):
    refs = parse_refs(ref, limit=1)
    if not refs:
        raise HTTPException(400, f"Could not parse reference: {ref!r}")
    return refs[0]


def _span(conn: sqlite3.Connection, ref: str) -> tuple[int, int, str]:
    """Resolve a reference to a stored span: clipped to real verses, with the
    label the reader should see. Everything that persists a span uses this, so
    a bookmark on "Psalm 121" matches the passage when it is read back."""
    r = _resolve(ref)
    start, end = R.clamp_span(conn, r.start, r.end)
    return start, end, R.span_label(conn, start, end)


@app.get("/api/passage")
def get_passage(
    ref: str = Query(..., description="e.g. 'Romans 8:28-30' or 'Psalm 23'"),
    translation: str = "BSB",
    compare: str = Query("", description="comma-separated translation abbreviations"),
    conn: sqlite3.Connection = Depends(db),
    user: dict | None = Depends(current_user_optional),
):
    r = _resolve(ref)
    passage = R.get_passage(conn, r.start, r.end, translation)
    if not passage:
        raise HTTPException(404, f"No text for {r.ref} in {translation}")

    others = [a.strip().upper() for a in compare.split(",") if a.strip()]
    comparisons = R.compare(conn, passage.start, passage.end, others) if others else {}

    out = {
        "ref": passage.ref,
        "book": passage.book,
        "book_name": BY_OSIS[passage.book].name,
        "genre": passage.genre,
        "title": passage.title,
        "translation": translation,
        "start": passage.start,
        "end": passage.end,
        "verses": [vars(v) for v in passage.verses],
        "comparisons": {k: [vars(v) for v in vs] for k, vs in comparisons.items()},
        "cross_refs": R.cross_refs_for(conn, passage.start, passage.end),
        "contested": [vars(c) for c in R.contested_for(conn, passage.start, passage.end)],
        "notes": [],
        "highlights": [],
        "bookmarked": False,
    }

    # The personal layer is overlaid only for a signed-in reader; signed out,
    # the same passage still reads normally.
    if user:
        uid = user["id"]
        out["notes"] = P.notes_for_span(conn, uid, passage.start, passage.end)
        out["highlights"] = P.highlights_for_span(conn, uid, passage.start, passage.end)
        # Bookmarks and history are keyed on the *stored* span for this
        # reference — the identical value _span() produced when they were
        # created — rather than on the bounds of whichever translation is being
        # read, which vary between texts.
        b_start, b_end, b_label = _span(conn, ref)
        out["bookmarked"] = P.is_bookmarked(conn, uid, b_start, b_end)
        P.record_reading(conn, uid, b_start, b_end, translation, ref=b_label)

    return out


@app.get("/api/chapter/{book}/{chapter}")
def get_chapter(
    book: str, chapter: int, translation: str = "BSB",
    conn: sqlite3.Connection = Depends(db),
    user: dict | None = Depends(current_user_optional),
):
    return get_passage(ref=f"{book} {chapter}", translation=translation, compare="",
                       conn=conn, user=user)


@app.get("/api/search")
def do_search(
    q: str = Query(..., min_length=2),
    k: int = Query(10, ge=1, le=40),
    translation: str = "BSB",
    conn: sqlite3.Connection = Depends(db),
):
    refs = parse_refs(q, limit=3)
    hits = R.search(conn, q, k=k)
    out = []
    for h in hits:
        preview = R.get_verses(conn, h.start, min(h.end, h.start + 2), translation)
        out.append({
            "ref": h.ref, "title": h.title, "score": h.score, "why": h.why,
            "start": h.start, "end": h.end,
            "preview": " ".join(v.text for v in preview)[:280],
        })
    return {"query": q, "references": [{"ref": r.ref} for r in refs], "results": out}


@app.get("/api/contested")
def get_contested(ref: str, conn: sqlite3.Connection = Depends(db)):
    r = _resolve(ref)
    return {"ref": r.ref, "contested": [vars(c) for c in R.contested_for(conn, r.start, r.end)]}


@app.get("/api/contested/all")
def all_contested(conn: sqlite3.Connection = Depends(db)):
    rows = conn.execute("SELECT * FROM contested ORDER BY start_vid").fetchall()
    out = []
    for r in rows:
        pos = conn.execute(
            "SELECT tradition, position FROM contested_positions WHERE contested_id=?",
            (r["id"],),
        ).fetchall()
        out.append({
            "ref": r["ref"], "topic": r["topic"], "question": r["question"],
            "positions": {p["tradition"]: p["position"] for p in pos},
        })
    return {"contested": out}


# ---------------------------------------------------------------------------
# accounts
# ---------------------------------------------------------------------------


@app.post("/api/auth/register")
def register(req: RegisterRequest, conn: sqlite3.Connection = Depends(db)):
    user = create_user(conn, req.email, req.password, req.display_name)
    return {"token": make_token(user["id"], user["email"]), "user": user}


@app.post("/api/auth/login")
def login(req: LoginRequest, conn: sqlite3.Connection = Depends(db)):
    user = authenticate(conn, req.email, req.password)
    return {"token": make_token(user["id"], user["email"]), "user": user}


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return {"user": user}


@app.patch("/api/settings")
def patch_settings(
    req: SettingsRequest,
    user: dict = Depends(current_user),
    conn: sqlite3.Connection = Depends(db),
):
    patch = {k: v for k, v in req.model_dump().items() if v is not None}
    return {"settings": P.update_settings(conn, user["id"], patch)}


# ---------------------------------------------------------------------------
# personal study data
# ---------------------------------------------------------------------------


@app.get("/api/notes")
def get_notes(
    q: str = "",
    user: dict = Depends(current_user),
    conn: sqlite3.Connection = Depends(db),
):
    notes = P.search_notes(conn, user["id"], q) if q else P.list_notes(conn, user["id"])
    return {"notes": notes}


@app.post("/api/notes")
def post_note(
    req: NoteRequest,
    user: dict = Depends(current_user),
    conn: sqlite3.Connection = Depends(db),
):
    start, end, label = _span(conn, req.ref)
    return {"note": P.create_note(conn, user["id"], start, end, req.body, ref=label)}


@app.patch("/api/notes/{note_id}")
def patch_note(
    note_id: int,
    req: NoteUpdate,
    user: dict = Depends(current_user),
    conn: sqlite3.Connection = Depends(db),
):
    note = P.update_note(conn, user["id"], note_id, req.body)
    if not note:
        raise HTTPException(404, "Note not found.")
    return {"note": note}


@app.delete("/api/notes/{note_id}")
def remove_note(
    note_id: int,
    user: dict = Depends(current_user),
    conn: sqlite3.Connection = Depends(db),
):
    if not P.delete_note(conn, user["id"], note_id):
        raise HTTPException(404, "Note not found.")
    return {"deleted": True}


@app.get("/api/highlights")
def get_highlights(user: dict = Depends(current_user), conn: sqlite3.Connection = Depends(db)):
    return {"highlights": P.list_highlights(conn, user["id"])}


@app.post("/api/highlights")
def post_highlight(
    req: HighlightRequest,
    user: dict = Depends(current_user),
    conn: sqlite3.Connection = Depends(db),
):
    start, end, label = _span(conn, req.ref)
    return {"highlight": P.create_highlight(conn, user["id"], start, end, req.color, ref=label)}


@app.delete("/api/highlights/{highlight_id}")
def remove_highlight(
    highlight_id: int,
    user: dict = Depends(current_user),
    conn: sqlite3.Connection = Depends(db),
):
    if not P.delete_highlight(conn, user["id"], highlight_id):
        raise HTTPException(404, "Highlight not found.")
    return {"deleted": True}


@app.get("/api/bookmarks")
def get_bookmarks(user: dict = Depends(current_user), conn: sqlite3.Connection = Depends(db)):
    return {"bookmarks": P.list_bookmarks(conn, user["id"])}


@app.post("/api/bookmarks")
def post_bookmark(
    req: BookmarkRequest,
    user: dict = Depends(current_user),
    conn: sqlite3.Connection = Depends(db),
):
    start, end, label = _span(conn, req.ref)
    return P.toggle_bookmark(conn, user["id"], start, end, req.label, ref=label)


@app.get("/api/history")
def get_history(user: dict = Depends(current_user), conn: sqlite3.Connection = Depends(db)):
    return {"history": P.list_history(conn, user["id"])}


@app.post("/api/history")
def post_history(
    req: HistoryRequest,
    user: dict = Depends(current_user),
    conn: sqlite3.Connection = Depends(db),
):
    start, end, label = _span(conn, req.ref)
    P.record_reading(conn, user["id"], start, end, req.translation, ref=label)
    return {"recorded": True}


@app.get("/api/conversations")
def get_conversations(user: dict = Depends(current_user), conn: sqlite3.Connection = Depends(db)):
    return {"conversations": P.list_sessions(conn, user["id"])}


@app.delete("/api/conversations/{session_id}")
def remove_conversation(
    session_id: str,
    user: dict = Depends(current_user),
    conn: sqlite3.Connection = Depends(db),
):
    if not P.delete_session(conn, user["id"], session_id):
        raise HTTPException(404, "Conversation not found.")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------


def _load_history(conn: sqlite3.Connection, session_id: str, limit: int = 12) -> list[dict]:
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


@app.post("/api/chat")
def chat(
    req: ChatRequest = Body(...),
    conn: sqlite3.Connection = Depends(db),
    user: dict | None = Depends(current_user_optional),
):
    uid = user["id"] if user else None

    # --- session
    sid = req.session_id or uuid.uuid4().hex
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO sessions (id, created_at, updated_at, translation, user_id)"
            " VALUES (?,?,?,?,?)",
            (sid, _now(), _now(), req.translation, uid),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    elif row["user_id"] is not None and row["user_id"] != uid:
        # Session ids are unguessable, but a conversation still belongs to the
        # account that started it.
        raise HTTPException(403, "This conversation belongs to another account.")
    elif row["user_id"] is None and uid is not None:
        # Signing in mid-conversation claims the anonymous session.
        conn.execute("UPDATE sessions SET user_id = ? WHERE id = ?", (uid, sid))
        conn.commit()

    # --- anchor: explicit from the client, else whatever the session was on
    anchor = None
    if req.anchor_ref:
        try:
            r = _resolve(req.anchor_ref)
            anchor = (r.start, r.end)
        except HTTPException:
            anchor = None
    elif row["anchor_start"]:
        anchor = (row["anchor_start"], row["anchor_end"])

    res = R.retrieve(
        conn, req.message, translation=req.translation,
        compare_with=req.compare, anchor=anchor,
        max_pericopes=config.settings.max_pericopes,
    )

    # The reader's own notes enter the prompt only when their setting allows.
    span = None
    if res.anchors:
        span = (res.anchors[0].start, res.anchors[0].end)
    elif res.hits:
        span = (res.hits[0].start, res.hits[0].end)
    if span:
        res.user_notes = P.notes_for_prompt(conn, user, span[0], span[1], req.message)

    context = build_context(res)

    # --- persist the turn and update the anchor
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)",
        (sid, "user", req.message, _now()),
    )
    new_anchor = (res.anchors[0].start, res.anchors[0].end) if res.anchors else anchor
    if new_anchor:
        conn.execute(
            "UPDATE sessions SET anchor_start=?, anchor_end=?, updated_at=?, translation=? WHERE id=?",
            (new_anchor[0], new_anchor[1], _now(), req.translation, sid),
        )
    conn.commit()

    history = _load_history(conn, sid)[:-1]  # exclude the message we just stored
    turn = f"{context}\n\n---\n\nReader's message: {req.message}"
    messages = [*history, {"role": "user", "content": turn}]

    provider = get_provider()
    citations = {
        "anchor": anchor_summary(res),
        "passages": [a.ref for a in res.anchors],
        "related": [h.ref for h in res.hits],
        "contested": [c.topic for c in res.contested],
        "translation": req.translation,
        # Surfaced so the UI can tell the reader when their notes were used.
        "used_notes": [n["ref"] for n in res.user_notes],
    }

    def gen():
        yield f"event: meta\ndata: {json.dumps({'session_id': sid, **citations})}\n\n"
        acc: list[str] = []
        try:
            for delta in provider.stream(SYSTEM, messages, max_tokens=2000):
                acc.append(delta)
                yield f"event: delta\ndata: {json.dumps({'text': delta})}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': f'{type(exc).__name__}: {exc}'})}\n\n"
        finally:
            text = "".join(acc)
            if text:
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, citations, created_at)"
                    " VALUES (?,?,?,?,?)",
                    (sid, "assistant", text, json.dumps(citations), _now()),
                )
                conn.commit()
            yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/session/{session_id}")
def get_session_endpoint(
    session_id: str,
    conn: sqlite3.Connection = Depends(db),
    user: dict | None = Depends(current_user_optional),
):
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        raise HTTPException(404, "session not found")
    owner = row["user_id"]
    if owner is not None and (not user or user["id"] != owner):
        raise HTTPException(403, "This conversation belongs to another account.")
    msgs = conn.execute(
        "SELECT role, content, citations, created_at FROM messages WHERE session_id=? ORDER BY id",
        (session_id,),
    ).fetchall()
    anchor = range_str(row["anchor_start"], row["anchor_end"]) if row["anchor_start"] else None
    return {
        "session_id": session_id,
        "anchor": anchor,
        "translation": row["translation"],
        "messages": [
            {"role": m["role"], "content": m["content"],
             "citations": json.loads(m["citations"]) if m["citations"] else None,
             "created_at": m["created_at"]}
            for m in msgs
        ],
    }


# ---------------------------------------------------------------------------
# static frontend
# ---------------------------------------------------------------------------
# Mounted last so it never shadows /api. When the frontend has been built, the
# whole product is one process; during development Vite proxies /api instead.

_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
