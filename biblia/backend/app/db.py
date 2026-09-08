"""SQLite schema and access layer.

SQLite is deliberate for the prototype: the whole corpus is a few hundred MB,
FTS5 gives production-grade BM25 for free, and the file is trivially portable.
Every query here is plain SQL against a stable schema, so moving to Postgres +
pgvector later is a driver swap, not a rewrite.

Verse identity
--------------
Every verse carries an integer `vid`:

    vid = book_order * 1_000_000 + chapter * 1_000 + verse

Book order is 1-66, chapters max at 150, verses at 176, so the encoding is
collision-free and *monotonic in canonical order*. That single property makes
passage ranges, "the next 5 verses", context windows and cross-reference spans
into plain integer BETWEEN queries instead of three-column comparisons.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .canon import BOOKS, BY_OSIS

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bible.db"

_ORDER = {b.osis: b.order for b in BOOKS}
_ORDER_INV = {b.order: b.osis for b in BOOKS}


def vid(book: str, chapter: int, verse: int) -> int:
    return _ORDER[book] * 1_000_000 + chapter * 1_000 + verse


def unvid(v: int) -> tuple[str, int, int]:
    order, rem = divmod(v, 1_000_000)
    chapter, verse = divmod(rem, 1_000)
    return _ORDER_INV[order], chapter, verse


def ref_str(v: int) -> str:
    book, ch, vs = unvid(v)
    return f"{BY_OSIS[book].name} {ch}:{vs}"


# Longest chapter in the canon is Psalm 119 at 176 verses. An end-verse at or
# above this means "to the end of the chapter" rather than a real verse number.
_OPEN_ENDED = 176


def range_str(start: int, end: int) -> str:
    """Human-readable reference for a verse span, e.g. 'Romans 8:28-30'.

    Spans that cover a whole chapter render as 'Psalms 23' rather than
    'Psalms 23:1-200', so open-ended lookups read naturally.
    """
    b1, c1, v1 = unvid(start)
    b2, c2, v2 = unvid(end)
    name = BY_OSIS[b1].name
    single_chapter = BY_OSIS[b1].chapters == 1

    if start == end:
        return f"{name} {c1}:{v1}" if not single_chapter else f"{name} {v1}"
    if b1 != b2:
        return f"{name} {c1}:{v1}-{BY_OSIS[b2].name} {c2}:{v2}"

    whole_start = v1 == 1
    whole_end = v2 >= _OPEN_ENDED
    if whole_start and whole_end:
        return f"{name} {c1}" if c1 == c2 else f"{name} {c1}-{c2}"
    if c1 == c2:
        return f"{name} {c1}:{v1}-{v2}" if not single_chapter else f"{name} {v1}-{v2}"
    return f"{name} {c1}:{v1}-{c2}:{v2}"


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS translations (
    id           INTEGER PRIMARY KEY,
    abbrev       TEXT UNIQUE NOT NULL,
    name         TEXT NOT NULL,
    year         TEXT,
    license      TEXT NOT NULL,
    language     TEXT NOT NULL DEFAULT 'en',
    -- where it sits on the formal-equivalence <-> dynamic-equivalence axis
    philosophy   TEXT,
    -- translation tradition/provenance, surfaced to the reader for transparency
    tradition    TEXT,
    notes        TEXT,
    is_reference INTEGER NOT NULL DEFAULT 0,
    sort_order   INTEGER NOT NULL DEFAULT 100,
    book_count   INTEGER NOT NULL DEFAULT 0,
    verse_count  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS verses (
    translation_id INTEGER NOT NULL REFERENCES translations(id) ON DELETE CASCADE,
    vid            INTEGER NOT NULL,
    book           TEXT    NOT NULL,
    chapter        INTEGER NOT NULL,
    verse          INTEGER NOT NULL,
    text           TEXT    NOT NULL,
    PRIMARY KEY (translation_id, vid)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_verses_vid  ON verses(vid);
CREATE INDEX IF NOT EXISTS idx_verses_book ON verses(book, chapter);

-- Lexical index. Only the reference translations are indexed: indexing all
-- translations makes near-duplicate wording of the same verse dominate the
-- result list and crowds out genuinely distinct passages.
CREATE VIRTUAL TABLE IF NOT EXISTS verses_fts USING fts5(
    text,
    vid UNINDEXED,
    translation_id UNINDEXED,
    tokenize = 'porter unicode61'
);

-- Pericopes: editorially-bounded passage units, the real unit of study.
CREATE TABLE IF NOT EXISTS pericopes (
    id         INTEGER PRIMARY KEY,
    book       TEXT    NOT NULL,
    start_vid  INTEGER NOT NULL,
    end_vid    INTEGER NOT NULL,
    title      TEXT    NOT NULL,
    level      INTEGER NOT NULL DEFAULT 1,
    parallel   TEXT,
    ref        TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pericope_span ON pericopes(start_vid, end_vid);
CREATE INDEX IF NOT EXISTS idx_pericope_book ON pericopes(book);

CREATE VIRTUAL TABLE IF NOT EXISTS pericopes_fts USING fts5(
    title, body,
    pericope_id UNINDEXED,
    tokenize = 'porter unicode61'
);

-- Dense vectors for pericopes, stored as raw float32. One embedding per
-- passage in the reference translation, never one per translation: the same
-- passage in 11 translations would otherwise occupy 11 near-identical points.
CREATE TABLE IF NOT EXISTS pericope_vectors (
    pericope_id INTEGER PRIMARY KEY REFERENCES pericopes(id) ON DELETE CASCADE,
    dim         INTEGER NOT NULL,
    vec         BLOB    NOT NULL
);

CREATE TABLE IF NOT EXISTS embedding_meta (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    provider TEXT NOT NULL,
    model    TEXT NOT NULL,
    dim      INTEGER NOT NULL,
    payload  BLOB
);

-- Cross-references between passages.
CREATE TABLE IF NOT EXISTS cross_refs (
    from_vid   INTEGER NOT NULL,
    to_start   INTEGER NOT NULL,
    to_end     INTEGER NOT NULL,
    votes      INTEGER NOT NULL DEFAULT 0,
    source     TEXT    NOT NULL DEFAULT 'bsb-parallel'
);
CREATE INDEX IF NOT EXISTS idx_xref_from ON cross_refs(from_vid);

-- Passages where interpretive traditions genuinely diverge. This is what
-- keeps the assistant honest: when retrieval lands inside one of these spans,
-- the prompt is required to present the range of readings rather than
-- silently picking one.
CREATE TABLE IF NOT EXISTS contested (
    id        INTEGER PRIMARY KEY,
    start_vid INTEGER NOT NULL,
    end_vid   INTEGER NOT NULL,
    ref       TEXT NOT NULL,
    topic     TEXT NOT NULL,
    question  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_contested_span ON contested(start_vid, end_vid);

CREATE TABLE IF NOT EXISTS contested_positions (
    contested_id INTEGER NOT NULL REFERENCES contested(id) ON DELETE CASCADE,
    tradition    TEXT NOT NULL,
    position     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cpos ON contested_positions(contested_id);

-- Conversation state, anchored to a passage under study.
CREATE TABLE IF NOT EXISTS sessions (
    id           TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    anchor_start INTEGER,
    anchor_end   INTEGER,
    translation  TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    citations  TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id, id);

-- ---------------------------------------------------------------------------
-- Accounts and personal study data
-- ---------------------------------------------------------------------------
-- Everything below is per-user and never shared. Reading the Bible works fully
-- signed out; an account only adds the personal layer on top.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id            INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    -- How much of the reader's own notes the assistant may see:
    --   never       notes are a reading feature only and never enter a prompt
    --   on_request  included only when the reader asks about their notes
    --   always      included whenever they are studying that passage
    -- Defaults to on_request: notes on scripture frequently hold confessions
    -- and prayers, and sending those to a model provider should be a choice
    -- the reader makes rather than one made for them.
    notes_visibility   TEXT NOT NULL DEFAULT 'on_request'
                       CHECK (notes_visibility IN ('never','on_request','always')),
    default_translation TEXT NOT NULL DEFAULT 'BSB',
    narrator_voice     TEXT,
    narrator_rate      REAL NOT NULL DEFAULT 0.95,
    narrator_pitch     REAL NOT NULL DEFAULT 1.0
);

-- Notes are anchored to a verse span rather than to a pericope id, so they
-- survive any future re-segmentation of the corpus.
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    start_vid  INTEGER NOT NULL,
    end_vid    INTEGER NOT NULL,
    ref        TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_user_span ON notes(user_id, start_vid, end_vid);

CREATE TABLE IF NOT EXISTS highlights (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    start_vid  INTEGER NOT NULL,
    end_vid    INTEGER NOT NULL,
    ref        TEXT NOT NULL,
    color      TEXT NOT NULL DEFAULT 'yellow',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hl_user_span ON highlights(user_id, start_vid, end_vid);

CREATE TABLE IF NOT EXISTS bookmarks (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    start_vid  INTEGER NOT NULL,
    end_vid    INTEGER NOT NULL,
    ref        TEXT NOT NULL,
    label      TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, start_vid, end_vid)
);

CREATE TABLE IF NOT EXISTS reading_history (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    start_vid   INTEGER NOT NULL,
    end_vid     INTEGER NOT NULL,
    ref         TEXT NOT NULL,
    translation TEXT NOT NULL,
    read_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hist_user ON reading_history(user_id, read_at DESC);
"""

# Columns added after the first release. SQLite has no "ADD COLUMN IF NOT
# EXISTS", so each is applied only when absent.
_MIGRATIONS: list[tuple[str, str, str]] = [
    ("sessions", "user_id", "ALTER TABLE sessions ADD COLUMN user_id INTEGER REFERENCES users(id)"),
    ("sessions", "title", "ALTER TABLE sessions ADD COLUMN title TEXT"),
]


def migrate(conn: sqlite3.Connection) -> None:
    for table, column, sql in _MIGRATIONS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if cols and column not in cols:
            conn.execute(sql)
    conn.commit()


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
    migrate(conn)
