"""Verification suite.

Run: pytest -q   (from backend/)

These tests check the things that are quietly catastrophic if wrong and easy
not to notice: a book silently missing, verse text bleeding across boundaries,
a reference parser that maps "3 John 4" to a chapter, pericopes that skip
verses. A Bible tool that returns the wrong verse is worse than one that
returns nothing.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.canon import BOOKS, BY_OSIS, KJV_TOTAL_VERSES, resolve_book
from app.db import DB_PATH, connect, range_str, unvid, vid
from app.retrieval import search as R
from app.retrieval.refparse import parse_refs

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="corpus not built")


@pytest.fixture(scope="module")
def conn() -> sqlite3.Connection:
    c = connect()
    yield c
    c.close()


# ---------------------------------------------------------------- canon


def test_canon_is_66_books_in_order():
    assert len(BOOKS) == 66
    assert [b.order for b in BOOKS] == list(range(1, 67))
    assert sum(1 for b in BOOKS if b.testament == "OT") == 39
    assert sum(1 for b in BOOKS if b.testament == "NT") == 27


def test_chapter_counts_match_known_values():
    known = {"Gen": 50, "Ps": 150, "Isa": 66, "Matt": 28, "John": 21,
             "Rom": 16, "Rev": 22, "Obad": 1, "Jude": 1, "3John": 1}
    for osis, n in known.items():
        assert BY_OSIS[osis].chapters == n, osis


def test_vid_roundtrip_and_ordering():
    assert unvid(vid("Rom", 8, 28)) == ("Rom", 8, 28)
    # canonical ordering must be monotonic in vid
    assert vid("Gen", 1, 1) < vid("Mal", 4, 6) < vid("Matt", 1, 1) < vid("Rev", 22, 21)
    # chapter and verse both order correctly
    assert vid("Ps", 23, 1) < vid("Ps", 23, 6) < vid("Ps", 24, 1)


@pytest.mark.parametrize("token,expected", [
    ("Genesis", "Gen"), ("gen", "Gen"), ("GEN", "Gen"),
    ("1 Cor", "1Cor"), ("first corinthians", "1Cor"), ("I Corinthians", "1Cor"),
    ("II Tim", "2Tim"), ("3 jn", "3John"), ("Song of Songs", "Song"),
    ("Psalm", "Ps"), ("psalms", "Ps"), ("Philemon", "Phlm"), ("Philippians", "Phil"),
    ("Revelation", "Rev"), ("Apocalypse", "Rev"), ("Qoheleth", "Eccl"),
])
def test_book_name_resolution(token, expected):
    assert resolve_book(token) == expected


# ------------------------------------------------------- reference parsing


@pytest.mark.parametrize("text,expected", [
    ("John 3:16", ["John 3:16"]),
    ("John 3:16-18", ["John 3:16-18"]),
    ("Jn 3.16", ["John 3:16"]),
    ("what does Romans 8:28 mean?", ["Romans 8:28"]),
    ("1 Cor 13:4-7", ["1 Corinthians 13:4-7"]),
    ("Gen 1:1-2:3", ["Genesis 1:1-2:3"]),
    ("Psalm 23", ["Psalms 23"]),
    ("Matt 5:3,5,9", ["Matthew 5:3", "Matthew 5:5", "Matthew 5:9"]),
    ("II Timothy 3:16", ["2 Timothy 3:16"]),
    ("Rom 8:28; Eph 1:4", ["Romans 8:28", "Ephesians 1:4"]),
    ("Philippians 4:6–7", ["Philippians 4:6-7"]),  # en dash
    ("Genesis 1-3", ["Genesis 1-3"]),
])
def test_reference_parsing(text, expected):
    assert [r.ref for r in parse_refs(text)] == expected


@pytest.mark.parametrize("text,expected", [
    ("3 Jn 4", ("3John", 1, 4)),
    ("Jude 3", ("Jude", 1, 3)),
    ("Philemon 6", ("Phlm", 1, 6)),
    ("Obadiah 15", ("Obad", 1, 15)),
])
def test_single_chapter_books_treat_bare_number_as_verse(text, expected):
    """'3 John 4' is verse 4, not chapter 4 — the book has one chapter."""
    r = parse_refs(text)[0]
    assert unvid(r.start) == expected


@pytest.mark.parametrize("text", [
    "I need help with anxiety",
    "the book of Job is hard to read",
    "",
    "what is grace",
])
def test_prose_does_not_produce_false_references(text):
    assert parse_refs(text) == []


def test_chapter_span_renders_without_phantom_verse():
    r = parse_refs("Psalm 23")[0]
    assert r.ref == "Psalms 23"  # not "Psalms 23:1-200"


# ------------------------------------------------------------ corpus data


def test_every_translation_loaded(conn):
    rows = conn.execute("SELECT abbrev, book_count, verse_count FROM translations").fetchall()
    assert len(rows) >= 10
    for r in rows:
        assert r["verse_count"] > 7_000, r["abbrev"]


def test_complete_translations_match_kjv_verse_total(conn):
    """KJV and ASV follow standard versification exactly; a drift here means
    the parser dropped or duplicated verses."""
    for abbrev in ("KJV", "ASV"):
        n = conn.execute(
            "SELECT verse_count FROM translations WHERE abbrev = ?", (abbrev,)
        ).fetchone()
        if n:
            assert n["verse_count"] == KJV_TOTAL_VERSES, abbrev


def test_all_66_books_present_in_reference_translations(conn):
    for abbrev in ("KJV", "BSB", "ASV"):
        rows = conn.execute(
            """SELECT DISTINCT book FROM verses v JOIN translations t ON t.id=v.translation_id
                WHERE t.abbrev = ?""",
            (abbrev,),
        ).fetchall()
        got = {r["book"] for r in rows}
        missing = {b.osis for b in BOOKS} - got
        assert not missing, f"{abbrev} missing {sorted(missing)}"


def test_no_verse_exceeds_its_books_chapter_count(conn):
    rows = conn.execute(
        "SELECT DISTINCT book, MAX(chapter) AS mx FROM verses GROUP BY book"
    ).fetchall()
    for r in rows:
        assert r["mx"] <= BY_OSIS[r["book"]].chapters, r["book"]


def test_no_empty_or_whitespace_verse_text(conn):
    n = conn.execute("SELECT COUNT(*) FROM verses WHERE TRIM(text) = ''").fetchone()[0]
    assert n == 0


def test_known_verses_read_correctly(conn):
    """Spot-check text that must be exact. A parser bug that merges adjacent
    verses shows up here immediately."""
    cases = [
        ("KJV", "John 3:16", "For God so loved the world"),
        ("KJV", "Genesis 1:1", "In the beginning God created the heaven and the earth."),
        ("KJV", "Psalm 23:1", "The LORD is my shepherd"),
        ("BSB", "John 11:35", "Jesus wept."),
        ("KJV", "Revelation 22:21", "The grace of our Lord Jesus Christ be with you all"),
    ]
    for abbrev, ref, expected in cases:
        r = parse_refs(ref)[0]
        verses = R.get_verses(conn, r.start, r.end, abbrev)
        assert verses, f"{ref} missing from {abbrev}"
        assert expected.lower() in verses[0].text.lower(), f"{abbrev} {ref}: {verses[0].text!r}"


def test_shortest_verse_is_not_contaminated(conn):
    """John 11:35 is two words. If verse-boundary handling leaks, this grows."""
    r = parse_refs("John 11:35")[0]
    v = R.get_verses(conn, r.start, r.end, "BSB")[0]
    assert len(v.text) < 30, v.text


# -------------------------------------------------------------- pericopes


def test_pericopes_are_well_formed(conn):
    rows = conn.execute("SELECT id, start_vid, end_vid, book, title FROM pericopes").fetchall()
    assert len(rows) > 1_000
    for r in rows:
        assert r["end_vid"] >= r["start_vid"], r["id"]
        assert r["end_vid"] % 1000 != 0, f"pericope {r['id']} ends at verse 0"
        assert r["title"].strip()


def test_pericopes_do_not_overlap(conn):
    rows = conn.execute(
        "SELECT start_vid, end_vid FROM pericopes ORDER BY start_vid"
    ).fetchall()
    for a, b in zip(rows, rows[1:]):
        assert a["end_vid"] < b["start_vid"], f"overlap at {range_str(a['start_vid'], a['end_vid'])}"


def test_every_pericope_contains_text(conn):
    empty = conn.execute(
        """SELECT COUNT(*) FROM pericopes p WHERE NOT EXISTS (
              SELECT 1 FROM verses v JOIN translations t ON t.id = v.translation_id
               WHERE t.abbrev = 'BSB' AND v.vid BETWEEN p.start_vid AND p.end_vid)"""
    ).fetchone()[0]
    assert empty == 0


# ------------------------------------------------------------- retrieval


def test_reference_query_anchors_exactly(conn):
    res = R.retrieve(conn, "What does Romans 8:28 mean?", translation="BSB")
    assert res.anchors and res.anchors[0].ref == "Romans 8:28"


def test_reference_query_does_not_return_book_name_noise(conn):
    """'Romans 8:28' must not surface Acts passages that mention Rome."""
    res = R.retrieve(conn, "What does Romans 8:28 mean?", translation="BSB")
    assert all(not h.ref.startswith("Acts") for h in res.hits)


def test_bare_reference_skips_search(conn):
    res = R.retrieve(conn, "John 3:16", translation="BSB")
    assert res.anchors
    assert res.hits == []


def test_thematic_search_finds_expected_passages(conn):
    cases = [
        ("verses about anxiety and worry", ("Philippians 4", "Matthew 6", "1 Peter 5")),
        ("the greatest of these is love", ("1 Corinthians 13",)),
        ("what does it mean to be born again", ("John 3",)),
    ]
    for query, expected_any in cases:
        hits = R.search(conn, query, k=8)
        refs = " | ".join(h.ref for h in hits)
        assert any(e in refs for e in expected_any), f"{query!r} -> {refs}"


def test_search_survives_fts_operator_injection(conn):
    """User text containing FTS5 operators must not error or change the query."""
    for q in ['love AND "quote', "faith OR NOT hope", "grace*", '"', "a:b", "^^^"]:
        R.search(conn, q, k=3)  # must not raise


def test_anchor_carries_across_turns(conn):
    """A follow-up with no reference of its own stays on the passage."""
    res = R.retrieve(conn, "what does he mean by that?", translation="BSB",
                     anchor=(vid("Rom", 8, 28), vid("Rom", 8, 30)))
    assert res.anchors and res.anchors[0].ref.startswith("Romans 8:28")


# ------------------------------------------------------------- contested


def test_all_contested_passages_resolved(conn):
    from app.ingest.contested import CONTESTED
    n = conn.execute("SELECT COUNT(*) FROM contested").fetchone()[0]
    assert n == len(CONTESTED), "some contested references failed to parse"


def test_contested_entries_have_multiple_traditions(conn):
    rows = conn.execute(
        """SELECT c.ref, COUNT(p.rowid) AS n FROM contested c
             JOIN contested_positions p ON p.contested_id = c.id
            GROUP BY c.id"""
    ).fetchall()
    for r in rows:
        assert r["n"] >= 2, f"{r['ref']} has only {r['n']} position(s)"


def test_contested_detected_by_overlap_not_containment(conn):
    """Asking about Romans 9:14 must surface the dispute registered for 9:6-24."""
    v = vid("Rom", 9, 14)
    assert R.contested_for(conn, v, v)


@pytest.mark.parametrize("ref,topic_fragment", [
    ("Romans 9:15", "Election"),
    ("Revelation 20:4", "millennium"),
    ("James 2:20", "Faith without works"),
    ("Matthew 16:18", "rock"),
])
def test_known_disputes_are_found(conn, ref, topic_fragment):
    r = parse_refs(ref)[0]
    topics = " ".join(c.topic for c in R.contested_for(conn, r.start, r.end))
    assert topic_fragment.lower() in topics.lower(), f"{ref} -> {topics!r}"


# ------------------------------------------------------------ prompt build


def test_context_block_carries_verse_text_and_disputes(conn):
    from app.llm.prompts import build_context
    res = R.retrieve(conn, "Does Romans 9 teach individual election?", translation="BSB")
    ctx = build_context(res)
    assert "Jacob I loved" in ctx
    assert "DISPUTED" in ctx
    assert "Reformed" in ctx and "Arminian" in ctx


def test_context_block_is_bounded(conn):
    from app.llm.prompts import build_context
    res = R.retrieve(conn, "Psalm 119", translation="BSB")  # longest chapter
    assert len(build_context(res)) <= 24_000


def test_empty_retrieval_instructs_against_fabrication(conn):
    from app.llm.prompts import build_context
    from app.retrieval.search import RetrievalResult
    ctx = build_context(RetrievalResult(query="zzzz"))
    assert "from memory" in ctx.lower()


# ------------------------------------------------------- span normalization


def test_clamp_span_clips_open_ended_reference(conn):
    """'Psalm 121' parses to an end of verse 200; storage needs the real end."""
    r = parse_refs("Psalm 121")[0]
    start, end = R.clamp_span(conn, r.start, r.end)
    assert unvid(start) == ("Ps", 121, 1)
    assert unvid(end) == ("Ps", 121, 8)


def test_clamp_span_ignores_other_versification(conn):
    """Regression: the Vulgate follows Septuagint psalm numbering, so its
    'Psalm 121' is the Hebrew Psalm 122 and has a verse 9. Clamping across all
    translations stretched every English psalm span by that difference, which
    made a bookmark created from 'Psalm 121' never match the passage again."""
    for ref, last_verse in [("Psalm 121", 8), ("Psalm 23", 6), ("Psalm 117", 2)]:
        r = parse_refs(ref)[0]
        _, end = R.clamp_span(conn, r.start, r.end)
        assert unvid(end)[2] == last_verse, f"{ref} clamped to verse {unvid(end)[2]}"


def test_span_label_renders_whole_chapters_naturally(conn):
    r = parse_refs("Psalm 121")[0]
    start, end = R.clamp_span(conn, r.start, r.end)
    assert R.span_label(conn, start, end) == "Psalms 121"
    # a partial span keeps its explicit range
    r2 = parse_refs("Psalm 121:1-3")[0]
    assert R.span_label(conn, r2.start, r2.end) == "Psalms 121:1-3"


def test_clamped_span_is_stable_across_repeat_resolution(conn):
    """Resolving the same reference twice must produce the same stored span —
    this is what lets a bookmark toggle off again."""
    for ref in ("Psalm 121", "Romans 8:28-30", "Jude 3", "Genesis 1"):
        r = parse_refs(ref)[0]
        assert R.clamp_span(conn, r.start, r.end) == R.clamp_span(conn, r.start, r.end)
