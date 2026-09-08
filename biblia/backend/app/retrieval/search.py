"""Retrieval: turn a question into the evidence the model is allowed to use.

Three retrieval modes run and are fused, because Bible questions arrive in
three shapes and no single mode handles all of them:

  reference   "what does Romans 8:28 mean"  -> exact span, deterministic
  lexical     "thou shalt not"               -> BM25 over verse text
  semantic    "verses about feeling anxious" -> dense vectors over pericopes

Reference hits are treated as *anchors* rather than as one ranked result among
many. If a user names a passage, that passage is the subject of the
conversation; a search result must not outrank it.

Lexical and semantic rankings are combined with reciprocal rank fusion, which
needs no score calibration between two very differently-scaled scorers.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from ..canon import BY_OSIS, GENRES
from ..db import range_str, unvid, vid
from .embed import VectorIndex
from .refparse import Ref, parse_refs

# ---------------------------------------------------------------------------
# result types
# ---------------------------------------------------------------------------


@dataclass
class Verse:
    vid: int
    book: str
    chapter: int
    verse: int
    text: str
    ref: str


@dataclass
class Passage:
    start: int
    end: int
    ref: str
    book: str
    genre: str
    title: str | None
    verses: list[Verse]
    translation: str

    def as_text(self) -> str:
        return " ".join(f"[{v.chapter}:{v.verse}] {v.text}" for v in self.verses)


@dataclass
class Hit:
    pericope_id: int
    start: int
    end: int
    ref: str
    title: str
    score: float
    why: str  # which retrieval mode surfaced this


@dataclass
class Contested:
    ref: str
    topic: str
    question: str
    positions: dict[str, str]


@dataclass
class RetrievalResult:
    query: str
    anchors: list[Passage] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    comparisons: dict[str, list[Verse]] = field(default_factory=dict)
    cross_refs: list[dict] = field(default_factory=list)
    contested: list[Contested] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # The reader's own study notes, attached only when their settings allow it.
    user_notes: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# FTS query sanitation
# ---------------------------------------------------------------------------

_WORD = re.compile(r"[A-Za-z']+")
_STOP = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "is", "it", "that",
    "this", "what", "does", "do", "did", "mean", "means", "meaning", "about",
    "for", "on", "with", "as", "by", "at", "be", "are", "was", "were", "i",
    "me", "my", "you", "your", "we", "us", "how", "why", "when", "who", "can",
    "should", "would", "verse", "verses", "bible", "say", "says", "passage",
}


def _fts_query(text: str, mode: str = "or") -> str | None:
    """Build a safe FTS5 MATCH expression from arbitrary user text.

    User input can contain FTS operators (AND, NOT, ", *, ^, :) that would
    either error or silently change the query, so every token is extracted and
    re-quoted rather than passed through.
    """
    words = [w.lower() for w in _WORD.findall(text or "")]
    words = [w for w in words if len(w) > 2 and w not in _STOP]
    if not words:
        return None
    words = words[:12]
    quoted = [f'"{w}"' for w in words]
    return (" OR " if mode == "or" else " ").join(quoted)


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------


def translations(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT abbrev, name, year, license, language, philosophy, tradition,"
        "       notes, is_reference, book_count, verse_count"
        "  FROM translations ORDER BY sort_order"
    )]


def _tid(conn: sqlite3.Connection, abbrev: str) -> int | None:
    r = conn.execute("SELECT id FROM translations WHERE abbrev = ?", (abbrev,)).fetchone()
    return r["id"] if r else None


def get_verses(
    conn: sqlite3.Connection, start: int, end: int, translation: str, limit: int = 400
) -> list[Verse]:
    tid = _tid(conn, translation)
    if tid is None:
        return []
    rows = conn.execute(
        """SELECT vid, book, chapter, verse, text FROM verses
            WHERE translation_id = ? AND vid BETWEEN ? AND ?
            ORDER BY vid LIMIT ?""",
        (tid, start, end, limit),
    ).fetchall()
    return [Verse(r["vid"], r["book"], r["chapter"], r["verse"], r["text"],
                  range_str(r["vid"], r["vid"])) for r in rows]


def clamp_span(conn: sqlite3.Connection, start: int, end: int) -> tuple[int, int]:
    """Clip a parsed span to verses that actually exist.

    The reference parser resolves an open-ended reference ("Psalm 121") to an
    end of verse 200, since it has no versification table. Storing that raw
    value is what makes a bookmark created from "Psalm 121" fail to match the
    same passage when it is read back, because reads report the real last
    verse. Everything that persists a span normalizes it here first.

    Clamping is done against the reference translation rather than against every
    translation at once. The Vulgate follows Septuagint psalm numbering, so its
    "Psalm 121" is the Hebrew Psalm 122 and runs to a verse 9 that does not
    exist for an English reader; a MAX across all translations would silently
    stretch every English psalm span by that difference.
    """
    from ..ingest.sources import REFERENCE

    for scope in (REFERENCE, None):
        sql = (
            "SELECT MIN(v.vid) AS lo, MAX(v.vid) AS hi FROM verses v"
            " JOIN translations t ON t.id = v.translation_id"
            " WHERE v.vid BETWEEN ? AND ?"
        )
        params: tuple = (start, end)
        if scope:
            sql += " AND t.abbrev = ?"
            params = (start, end, scope)
        row = conn.execute(sql, params).fetchone()
        if row and row["lo"] is not None:
            return row["lo"], row["hi"]
    return start, end


def span_label(conn: sqlite3.Connection, start: int, end: int) -> str:
    """Display label for a span, preferring 'Psalms 121' over 'Psalms 121:1-8'
    when the span covers a whole chapter."""
    from ..ingest.sources import REFERENCE

    book, chapter, _ = unvid(start)
    row = conn.execute(
        "SELECT MIN(v.vid) AS lo, MAX(v.vid) AS hi FROM verses v"
        "  JOIN translations t ON t.id = v.translation_id"
        " WHERE v.vid BETWEEN ? AND ? AND t.abbrev = ?",
        (vid(book, chapter, 1), vid(book, chapter, 999), REFERENCE),
    ).fetchone()
    if row and row["lo"] == start and row["hi"] == end:
        return f"{BY_OSIS[book].name} {chapter}"
    return range_str(start, end)


def pericope_for(conn: sqlite3.Connection, v: int) -> dict | None:
    r = conn.execute(
        """SELECT * FROM pericopes
            WHERE start_vid <= ? AND end_vid >= ?
            ORDER BY (end_vid - start_vid) ASC LIMIT 1""",
        (v, v),
    ).fetchone()
    return dict(r) if r else None


def get_passage(
    conn: sqlite3.Connection, start: int, end: int, translation: str
) -> Passage | None:
    verses = get_verses(conn, start, end, translation)
    if not verses:
        return None
    book = verses[0].book
    per = pericope_for(conn, start)
    real_end = verses[-1].vid

    # An open-ended request ("Psalm 23") that was satisfied from verse 1 is a
    # whole chapter, and should display as "Psalms 23" rather than as the
    # clipped span "Psalms 23:1-6". Anything else displays its actual extent.
    open_ended = end % 1_000 >= 176 and verses[0].verse == 1
    ref = range_str(verses[0].vid, end if open_ended else real_end)

    return Passage(
        start=verses[0].vid, end=real_end, ref=ref,
        book=book, genre=GENRES.get(BY_OSIS[book].genre, ""),
        title=per["title"] if per else None,
        verses=verses, translation=translation,
    )


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def _lexical_pericopes(conn: sqlite3.Connection, query: str, k: int) -> list[tuple[int, float]]:
    q = _fts_query(query)
    if not q:
        return []
    try:
        rows = conn.execute(
            """SELECT pericope_id, bm25(pericopes_fts, 3.0, 1.0) AS score
                 FROM pericopes_fts WHERE pericopes_fts MATCH ?
                 ORDER BY score LIMIT ?""",
            (q, k),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [(r["pericope_id"], -r["score"]) for r in rows]


def _lexical_verses(conn: sqlite3.Connection, query: str, k: int) -> list[tuple[int, float]]:
    """Verse-level BM25, mapped up to the containing pericope.

    Phrase-ish matching first (all terms), then OR as a fallback, so an exact
    quotation ranks above a bag-of-words overlap.
    """
    for mode in ("and", "or"):
        q = _fts_query(query, mode)
        if not q:
            return []
        if mode == "and":
            q = q.replace(" ", " AND ") if " " in q else q
        try:
            rows = conn.execute(
                """SELECT vid, bm25(verses_fts) AS score
                     FROM verses_fts WHERE verses_fts MATCH ?
                     ORDER BY score LIMIT ?""",
                (q, k * 2),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if rows:
            out: dict[int, float] = {}
            for r in rows:
                per = pericope_for(conn, r["vid"])
                if per and per["id"] not in out:
                    out[per["id"]] = -r["score"]
            if out:
                return sorted(out.items(), key=lambda kv: -kv[1])[:k]
    return []


_INDEX: VectorIndex | None = None


def vector_index(conn: sqlite3.Connection) -> VectorIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = VectorIndex(conn)
    return _INDEX


def _rrf(rankings: list[list[tuple[int, float]]], weights: list[float], k: int = 60) -> dict[int, float]:
    """Reciprocal rank fusion. Uses rank position, not raw score, so BM25 and
    cosine similarity can be combined without calibrating their scales."""
    fused: dict[int, float] = {}
    for ranking, w in zip(rankings, weights):
        for rank, (pid, _score) in enumerate(ranking, start=1):
            fused[pid] = fused.get(pid, 0.0) + w / (k + rank)
    return fused


def search(conn: sqlite3.Connection, query: str, k: int = 8) -> list[Hit]:
    lex_p = _lexical_pericopes(conn, query, k * 3)
    lex_v = _lexical_verses(conn, query, k * 3)
    vec = vector_index(conn).search(query, k * 3)

    fused = _rrf([lex_v, lex_p, vec], [1.0, 0.7, 0.9])
    if not fused:
        return []

    origin: dict[int, list[str]] = {}
    for name, ranking in (("quotation", lex_v), ("keyword", lex_p), ("theme", vec)):
        for pid, _ in ranking[:k * 2]:
            origin.setdefault(pid, []).append(name)

    top = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
    out: list[Hit] = []
    for pid, score in top:
        r = conn.execute("SELECT * FROM pericopes WHERE id = ?", (pid,)).fetchone()
        if not r:
            continue
        out.append(Hit(pid, r["start_vid"], r["end_vid"], r["ref"], r["title"],
                       round(score, 5), "+".join(origin.get(pid, ["fused"]))))
    return out


# ---------------------------------------------------------------------------
# enrichment
# ---------------------------------------------------------------------------


def cross_refs_for(conn: sqlite3.Connection, start: int, end: int, limit: int = 8) -> list[dict]:
    rows = conn.execute(
        """SELECT to_start, to_end, votes FROM cross_refs
            WHERE from_vid BETWEEN ? AND ?
            ORDER BY votes DESC LIMIT ?""",
        (start, end, limit),
    ).fetchall()
    seen, out = set(), []
    for r in rows:
        key = (r["to_start"], r["to_end"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"start": r["to_start"], "end": r["to_end"],
                    "ref": range_str(r["to_start"], r["to_end"])})
    return out


def contested_for(conn: sqlite3.Connection, start: int, end: int) -> list[Contested]:
    """Interpretive disputes overlapping a span.

    Overlap, not containment: asking about Romans 9:14 should surface the
    dispute registered for Romans 9:6-24.
    """
    rows = conn.execute(
        """SELECT * FROM contested
            WHERE start_vid <= ? AND end_vid >= ?
            ORDER BY (end_vid - start_vid) ASC""",
        (end, start),
    ).fetchall()
    out = []
    for r in rows:
        pos = conn.execute(
            "SELECT tradition, position FROM contested_positions WHERE contested_id = ?",
            (r["id"],),
        ).fetchall()
        out.append(Contested(r["ref"], r["topic"], r["question"],
                             {p["tradition"]: p["position"] for p in pos}))
    return out


def compare(
    conn: sqlite3.Connection, start: int, end: int, abbrevs: list[str]
) -> dict[str, list[Verse]]:
    return {a: get_verses(conn, start, end, a, limit=120) for a in abbrevs}


# ---------------------------------------------------------------------------
# top-level: assemble everything a turn needs
# ---------------------------------------------------------------------------


def retrieve(
    conn: sqlite3.Connection,
    query: str,
    translation: str = "BSB",
    compare_with: list[str] | None = None,
    anchor: tuple[int, int] | None = None,
    max_pericopes: int = 4,
) -> RetrievalResult:
    """Assemble the evidence bundle for one conversational turn.

    `anchor` carries the passage already under study, so follow-up questions
    ("what about the next verse?", "who is 'he' here?") stay attached to the
    passage instead of re-searching the whole canon on a pronoun.
    """
    res = RetrievalResult(query=query)
    compare_with = compare_with or []

    refs: list[Ref] = parse_refs(query, limit=4)
    spans: list[tuple[int, int]] = [(r.start, r.end) for r in refs]

    # Strip the reference text itself before searching. Left in, "Romans 8:28"
    # makes BM25 rank every passage containing the word "Romans", which buries
    # the actual topic under Acts narratives about Rome.
    residual = query
    for r in refs:
        residual = residual.replace(r.raw, " ")
    residual = residual.strip()

    # Fall back to the conversation's existing anchor when the message names
    # no passage of its own.
    if not spans and anchor:
        spans = [anchor]
        res.notes.append("continuing with the passage already under study")

    for start, end in spans[:3]:
        p = get_passage(conn, start, end, translation)
        if p:
            res.anchors.append(p)

    # Search only on what is left after the reference is removed. If nothing
    # substantive remains ("John 3:16", "Psalm 23"), the user wants to read a
    # passage, not to search — returning unrelated hits would be noise.
    search_text = residual if refs else query
    if _fts_query(search_text):
        # With a passage already anchored, related hits are supporting material
        # rather than the answer, so keep the list short. Unanchored questions
        # depend entirely on search and get the full budget.
        k = 3 if res.anchors else max_pericopes
        for h in search(conn, search_text, k=k + 2):
            if any(h.start <= a.end and h.end >= a.start for a in res.anchors):
                continue  # already covered by an anchor
            res.hits.append(h)
            if len(res.hits) >= k:
                break

    # Enrichment is anchored on the primary passage, or the top hit.
    if res.anchors:
        prim = (res.anchors[0].start, res.anchors[0].end)
    elif res.hits:
        prim = (res.hits[0].start, res.hits[0].end)
    else:
        prim = None

    if prim:
        res.cross_refs = cross_refs_for(conn, *prim)
        res.contested = contested_for(conn, *prim)
        if compare_with:
            res.comparisons = compare(conn, prim[0], min(prim[1], prim[0] + 30), compare_with)

    return res
