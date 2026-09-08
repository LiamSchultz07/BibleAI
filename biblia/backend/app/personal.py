"""Per-user study data: notes, highlights, bookmarks, reading history.

Two rules hold throughout this module.

**Ownership is enforced in the WHERE clause, never checked afterward.** Every
read and write is scoped by `user_id` in the query itself, so a request for
someone else's note id returns nothing rather than returning a row that some
later branch is responsible for rejecting. Ownership bugs happen when the check
is a separate step from the fetch.

**Anchors are verse spans, not pericope ids.** A note attached to pericope #412
would silently point somewhere else if the corpus were ever re-segmented; a note
attached to `Romans 8:28-30` cannot.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

from .db import range_str

HIGHLIGHT_COLORS = ("yellow", "green", "blue", "pink", "orange", "purple")

# Phrases by which a reader asks the assistant to look at their own notes.
# Used only in the 'on_request' visibility mode.
_NOTE_REQUEST = re.compile(
    r"\b(my|our)\s+(note|notes|journal|highlight|highlights|annotation|annotations)\b"
    r"|\bwhat\s+(did|have)\s+i\s+(write|written|note|noted|say|said)\b"
    r"|\bi\s+(wrote|noted|journaled)\b"
    r"|\bmy\s+(earlier|previous|past)\s+(thought|thoughts|study|reflection|reflections)\b",
    re.IGNORECASE,
)


def asks_about_notes(message: str) -> bool:
    return bool(_NOTE_REQUEST.search(message or ""))


def notes_for_prompt(
    conn: sqlite3.Connection,
    user: dict | None,
    start: int,
    end: int,
    message: str,
) -> list[dict]:
    """Decide whether the reader's notes may enter this turn's prompt.

    The default is 'on_request', so notes stay out of prompts unless the reader
    either asks for them or has opted into always sharing. Nothing here ever
    reaches a model provider without the reader's setting permitting it.
    """
    if not user:
        return []
    mode = (user.get("settings") or {}).get("notes_visibility", "on_request")
    if mode == "never":
        return []
    if mode == "on_request" and not asks_about_notes(message):
        return []
    return notes_for_span(conn, user["id"], start, end)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# notes
# ---------------------------------------------------------------------------


def list_notes(conn: sqlite3.Connection, user_id: int, limit: int = 200) -> list[dict]:
    rows = conn.execute(
        """SELECT id, start_vid, end_vid, ref, body, created_at, updated_at
             FROM notes WHERE user_id = ? ORDER BY start_vid LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def notes_for_span(
    conn: sqlite3.Connection, user_id: int, start: int, end: int
) -> list[dict]:
    """Notes overlapping a span — a note on Romans 8:28-30 surfaces when
    reading Romans 8:29."""
    rows = conn.execute(
        """SELECT id, start_vid, end_vid, ref, body, created_at, updated_at
             FROM notes
            WHERE user_id = ? AND start_vid <= ? AND end_vid >= ?
            ORDER BY start_vid""",
        (user_id, end, start),
    ).fetchall()
    return [dict(r) for r in rows]


def create_note(
    conn: sqlite3.Connection, user_id: int, start: int, end: int, body: str,
    ref: str | None = None,
) -> dict:
    now = _now()
    ref = ref or range_str(start, end)
    cur = conn.execute(
        """INSERT INTO notes (user_id, start_vid, end_vid, ref, body, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?)""",
        (user_id, start, end, ref, body.strip(), now, now),
    )
    conn.commit()
    return get_note(conn, user_id, cur.lastrowid)


def get_note(conn: sqlite3.Connection, user_id: int, note_id: int) -> dict | None:
    r = conn.execute(
        """SELECT id, start_vid, end_vid, ref, body, created_at, updated_at
             FROM notes WHERE id = ? AND user_id = ?""",
        (note_id, user_id),
    ).fetchone()
    return dict(r) if r else None


def update_note(
    conn: sqlite3.Connection, user_id: int, note_id: int, body: str
) -> dict | None:
    conn.execute(
        "UPDATE notes SET body = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (body.strip(), _now(), note_id, user_id),
    )
    conn.commit()
    return get_note(conn, user_id, note_id)


def delete_note(conn: sqlite3.Connection, user_id: int, note_id: int) -> bool:
    cur = conn.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
    conn.commit()
    return cur.rowcount > 0


def search_notes(conn: sqlite3.Connection, user_id: int, q: str, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        """SELECT id, start_vid, end_vid, ref, body, created_at, updated_at
             FROM notes WHERE user_id = ? AND body LIKE ?
            ORDER BY updated_at DESC LIMIT ?""",
        (user_id, f"%{q}%", limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# highlights
# ---------------------------------------------------------------------------


def highlights_for_span(
    conn: sqlite3.Connection, user_id: int, start: int, end: int
) -> list[dict]:
    rows = conn.execute(
        """SELECT id, start_vid, end_vid, ref, color, created_at FROM highlights
            WHERE user_id = ? AND start_vid <= ? AND end_vid >= ?""",
        (user_id, end, start),
    ).fetchall()
    return [dict(r) for r in rows]


def list_highlights(conn: sqlite3.Connection, user_id: int, limit: int = 300) -> list[dict]:
    rows = conn.execute(
        """SELECT id, start_vid, end_vid, ref, color, created_at FROM highlights
            WHERE user_id = ? ORDER BY start_vid LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def create_highlight(
    conn: sqlite3.Connection, user_id: int, start: int, end: int, color: str,
    ref: str | None = None,
) -> dict:
    color = color if color in HIGHLIGHT_COLORS else "yellow"
    ref = ref or range_str(start, end)
    # Re-highlighting the same span recolors it rather than stacking overlays.
    existing = conn.execute(
        "SELECT id FROM highlights WHERE user_id = ? AND start_vid = ? AND end_vid = ?",
        (user_id, start, end),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE highlights SET color = ? WHERE id = ? AND user_id = ?",
            (color, existing["id"], user_id),
        )
        conn.commit()
        hid = existing["id"]
    else:
        cur = conn.execute(
            """INSERT INTO highlights (user_id, start_vid, end_vid, ref, color, created_at)
               VALUES (?,?,?,?,?,?)""",
            (user_id, start, end, ref, color, _now()),
        )
        conn.commit()
        hid = cur.lastrowid
    r = conn.execute(
        "SELECT id, start_vid, end_vid, ref, color, created_at FROM highlights WHERE id = ?",
        (hid,),
    ).fetchone()
    return dict(r)


def delete_highlight(conn: sqlite3.Connection, user_id: int, highlight_id: int) -> bool:
    cur = conn.execute(
        "DELETE FROM highlights WHERE id = ? AND user_id = ?", (highlight_id, user_id)
    )
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# bookmarks
# ---------------------------------------------------------------------------


def list_bookmarks(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT id, start_vid, end_vid, ref, label, created_at FROM bookmarks
            WHERE user_id = ? ORDER BY created_at DESC""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def toggle_bookmark(
    conn: sqlite3.Connection, user_id: int, start: int, end: int, label: str | None,
    ref: str | None = None,
) -> dict:
    ref = ref or range_str(start, end)
    existing = conn.execute(
        "SELECT id FROM bookmarks WHERE user_id = ? AND start_vid = ? AND end_vid = ?",
        (user_id, start, end),
    ).fetchone()
    if existing:
        conn.execute(
            "DELETE FROM bookmarks WHERE id = ? AND user_id = ?", (existing["id"], user_id)
        )
        conn.commit()
        return {"bookmarked": False, "ref": ref}
    conn.execute(
        """INSERT INTO bookmarks (user_id, start_vid, end_vid, ref, label, created_at)
           VALUES (?,?,?,?,?,?)""",
        (user_id, start, end, ref, label, _now()),
    )
    conn.commit()
    return {"bookmarked": True, "ref": ref}


def is_bookmarked(conn: sqlite3.Connection, user_id: int, start: int, end: int) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM bookmarks WHERE user_id = ? AND start_vid = ? AND end_vid = ?",
        (user_id, start, end),
    ).fetchone())


# ---------------------------------------------------------------------------
# reading history
# ---------------------------------------------------------------------------


def record_reading(
    conn: sqlite3.Connection, user_id: int, start: int, end: int, translation: str,
    ref: str | None = None,
) -> None:
    """Record a passage view, collapsing immediate repeats.

    Re-opening the same passage (a translation switch, a page refresh) updates
    the existing entry instead of filling the history with duplicates.
    """
    ref = ref or range_str(start, end)
    last = conn.execute(
        "SELECT id, start_vid, end_vid FROM reading_history WHERE user_id = ?"
        " ORDER BY read_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if last and last["start_vid"] == start and last["end_vid"] == end:
        conn.execute(
            "UPDATE reading_history SET read_at = ?, translation = ? WHERE id = ?",
            (_now(), translation, last["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO reading_history (user_id, start_vid, end_vid, ref, translation, read_at)
               VALUES (?,?,?,?,?,?)""",
            (user_id, start, end, ref, translation, _now()),
        )
        # keep history bounded
        conn.execute(
            """DELETE FROM reading_history WHERE user_id = ? AND id NOT IN (
                   SELECT id FROM reading_history WHERE user_id = ?
                    ORDER BY read_at DESC LIMIT 500)""",
            (user_id, user_id),
        )
    conn.commit()


def list_history(conn: sqlite3.Connection, user_id: int, limit: int = 30) -> list[dict]:
    rows = conn.execute(
        """SELECT id, start_vid, end_vid, ref, translation, read_at FROM reading_history
            WHERE user_id = ? ORDER BY read_at DESC LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# saved conversations
# ---------------------------------------------------------------------------


def list_sessions(conn: sqlite3.Connection, user_id: int, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        """SELECT s.id, s.created_at, s.updated_at, s.anchor_start, s.anchor_end,
                  s.translation, s.title,
                  (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count,
                  (SELECT content FROM messages m WHERE m.session_id = s.id
                    AND m.role = 'user' ORDER BY m.id LIMIT 1) AS opening
             FROM sessions s
            WHERE s.user_id = ?
              AND EXISTS (SELECT 1 FROM messages m WHERE m.session_id = s.id)
            ORDER BY s.updated_at DESC LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["anchor"] = (
            range_str(r["anchor_start"], r["anchor_end"]) if r["anchor_start"] else None
        )
        # A conversation's title is its opening question unless one was set.
        if not d.get("title"):
            opening = (d.get("opening") or "").strip().replace("\n", " ")
            d["title"] = (opening[:70] + "…") if len(opening) > 70 else (opening or "Untitled")
        d.pop("opening", None)
        out.append(d)
    return out


def delete_session(conn: sqlite3.Connection, user_id: int, session_id: str) -> bool:
    cur = conn.execute(
        "DELETE FROM sessions WHERE id = ? AND user_id = ?", (session_id, user_id)
    )
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

_SETTING_FIELDS = {
    "notes_visibility": lambda v: v if v in ("never", "on_request", "always") else None,
    "default_translation": lambda v: str(v)[:16] if v else None,
    "narrator_voice": lambda v: str(v)[:120] if v else None,
    "narrator_rate": lambda v: min(max(float(v), 0.5), 2.0),
    "narrator_pitch": lambda v: min(max(float(v), 0.5), 2.0),
}


def update_settings(conn: sqlite3.Connection, user_id: int, patch: dict) -> dict:
    sets, vals = [], []
    for key, coerce in _SETTING_FIELDS.items():
        if key not in patch:
            continue
        try:
            value = coerce(patch[key])
        except (TypeError, ValueError):
            continue
        if value is None and key != "narrator_voice":
            continue
        sets.append(f"{key} = ?")
        vals.append(value)
    if sets:
        conn.execute(
            f"UPDATE user_settings SET {', '.join(sets)} WHERE user_id = ?", (*vals, user_id)
        )
        conn.commit()
    row = conn.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    return {k: row[k] for k in row.keys() if k != "user_id"}
