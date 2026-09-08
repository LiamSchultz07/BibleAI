"""Corpus build: XML sources -> queryable SQLite.

Run with:
    python -m app.ingest.run --source-dir /path/to/open-bibles

Stages
------
1. verses        every translation, normalized to OSIS ids and integer vids
2. pericopes     passage units derived from the reference text's section headings
3. lexical       FTS5 indexes over verses and pericope bodies
4. cross-refs    parallel-passage notes carried in the reference text
5. contested     the curated interpretive-disagreement map
6. embeddings    dense vectors, one per pericope (see retrieval.embed)

Stages are idempotent: re-running replaces prior content for the affected
tables rather than duplicating it.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

from ..canon import BY_OSIS
from ..db import connect, init, range_str, vid
from ..retrieval.refparse import parse_refs
from .contested import CONTESTED
from .parsers import ParsedHeading, ParsedVerse, parse
from .sources import INDEXED, REFERENCE, SOURCES, Source


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# stage 1: verses
# ---------------------------------------------------------------------------


def ingest_translation(
    conn: sqlite3.Connection, src: Source, path: Path
) -> tuple[int, list[ParsedHeading]]:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO translations
             (abbrev, name, year, license, language, philosophy, tradition,
              notes, is_reference, sort_order)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(abbrev) DO UPDATE SET
             name=excluded.name, year=excluded.year, license=excluded.license,
             philosophy=excluded.philosophy, tradition=excluded.tradition,
             notes=excluded.notes, is_reference=excluded.is_reference,
             sort_order=excluded.sort_order""",
        (src.abbrev, src.name, src.year, src.license, src.language,
         src.philosophy, src.tradition, src.notes, int(src.is_reference), src.sort_order),
    )
    tid = cur.execute(
        "SELECT id FROM translations WHERE abbrev = ?", (src.abbrev,)
    ).fetchone()[0]

    cur.execute("DELETE FROM verses WHERE translation_id = ?", (tid,))

    rows: list[tuple] = []
    headings: list[ParsedHeading] = []
    skipped = 0

    for rec in parse(str(path), src.fmt):
        if isinstance(rec, ParsedHeading):
            headings.append(rec)
            continue
        b = BY_OSIS.get(rec.book)
        if not b or rec.chapter < 1 or rec.verse < 1:
            skipped += 1
            continue
        if rec.chapter > b.chapters:
            skipped += 1
            continue
        rows.append((tid, vid(rec.book, rec.chapter, rec.verse),
                     rec.book, rec.chapter, rec.verse, rec.text))

    cur.executemany(
        "INSERT OR REPLACE INTO verses (translation_id, vid, book, chapter, verse, text)"
        " VALUES (?,?,?,?,?,?)",
        rows,
    )
    books = cur.execute(
        "SELECT COUNT(DISTINCT book) FROM verses WHERE translation_id = ?", (tid,)
    ).fetchone()[0]
    cur.execute(
        "UPDATE translations SET book_count = ?, verse_count = ? WHERE id = ?",
        (books, len(rows), tid),
    )
    conn.commit()

    note = f"  ({skipped} out-of-canon records skipped)" if skipped else ""
    log(f"  {src.abbrev:7} {len(rows):>6} verses  {books:>2} books{note}")
    return tid, headings


# ---------------------------------------------------------------------------
# stage 2: pericopes
# ---------------------------------------------------------------------------


def build_pericopes(conn: sqlite3.Connection, headings: list[ParsedHeading]) -> int:
    """Turn section headings into contiguous passage spans.

    Headings mark starts, so each pericope runs to the verse before the next
    heading in the same book. Nested headings that share a start verse are
    merged into one title rather than producing empty spans.
    """
    cur = conn.cursor()
    cur.execute("DELETE FROM pericopes")

    # collapse headings that begin at the same verse (s1 immediately followed by s2)
    merged: dict[int, ParsedHeading] = {}
    for h in headings:
        b = BY_OSIS.get(h.book)
        if not b or h.chapter < 1 or h.chapter > b.chapters or h.after_verse < 1:
            continue
        key = vid(h.book, h.chapter, h.after_verse)
        if key in merged:
            prev = merged[key]
            if h.title.lower() not in prev.title.lower():
                prev.title = f"{prev.title} — {h.title}"
            prev.parallel = prev.parallel or h.parallel
        else:
            merged[key] = ParsedHeading(h.book, h.chapter, h.after_verse,
                                        h.level, h.title, h.parallel)

    # Resolve ends against real verse data rather than by decrementing the next
    # start. A pericope that runs to a chapter boundary would otherwise end at
    # "23:0", since the next one begins at 23:1 and there is no verse 0.
    ref_tid = cur.execute(
        "SELECT id FROM translations WHERE abbrev = ?", (REFERENCE,)
    ).fetchone()

    def last_vid_before(limit: int, floor: int) -> int | None:
        if not ref_tid:
            return None
        r = cur.execute(
            "SELECT MAX(vid) AS v FROM verses WHERE translation_id = ? AND vid < ? AND vid >= ?",
            (ref_tid[0], limit, floor),
        ).fetchone()
        return r["v"] if r and r["v"] else None

    def last_vid_in_book(book: str) -> int | None:
        if not ref_tid:
            return None
        r = cur.execute(
            "SELECT MAX(vid) AS v FROM verses WHERE translation_id = ? AND book = ?",
            (ref_tid[0], book),
        ).fetchone()
        return r["v"] if r and r["v"] else None

    starts = sorted(merged)
    rows = []
    for i, s in enumerate(starts):
        h = merged[s]
        b = BY_OSIS[h.book]
        end = None
        if i + 1 < len(starts):
            nxt = starts[i + 1]
            if merged[nxt].book == h.book:
                end = last_vid_before(nxt, s)
        if end is None:
            # last pericope in the book
            end = last_vid_in_book(h.book) or vid(h.book, b.chapters, 200)
        if end < s:
            end = s
        rows.append((h.book, s, end, h.title, h.level, h.parallel, range_str(s, end)))

    cur.executemany(
        "INSERT INTO pericopes (book, start_vid, end_vid, title, level, parallel, ref)"
        " VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    log(f"  {len(rows)} pericopes")
    return len(rows)


# ---------------------------------------------------------------------------
# stage 3: lexical indexes
# ---------------------------------------------------------------------------


def build_fts(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM verses_fts")
    placeholders = ",".join("?" for _ in INDEXED)
    cur.execute(
        f"""INSERT INTO verses_fts (text, vid, translation_id)
            SELECT v.text, v.vid, v.translation_id
              FROM verses v JOIN translations t ON t.id = v.translation_id
             WHERE t.abbrev IN ({placeholders})""",
        INDEXED,
    )
    n = cur.execute("SELECT COUNT(*) FROM verses_fts").fetchone()[0]

    # pericope bodies come from the reference translation
    cur.execute("DELETE FROM pericopes_fts")
    cur.execute(
        """INSERT INTO pericopes_fts (title, body, pericope_id)
           SELECT p.title,
                  (SELECT group_concat(v.text, ' ')
                     FROM verses v
                     JOIN translations t ON t.id = v.translation_id
                    WHERE t.abbrev = ?
                      AND v.vid BETWEEN p.start_vid AND p.end_vid),
                  p.id
             FROM pericopes p""",
        (REFERENCE,),
    )
    m = cur.execute("SELECT COUNT(*) FROM pericopes_fts").fetchone()[0]
    conn.commit()
    log(f"  lexical index: {n} verses ({'+'.join(INDEXED)}), {m} pericopes")


# ---------------------------------------------------------------------------
# stage 4: cross references
# ---------------------------------------------------------------------------


def build_crossrefs(conn: sqlite3.Connection) -> int:
    """Extract cross-references from the reference text's parallel-passage notes.

    These are editorial notes already present in the corpus ("(John 1:1-5;
    Hebrews 11:1-3)" under a section heading), so they carry the same open
    license as the text itself.
    """
    cur = conn.cursor()
    cur.execute("DELETE FROM cross_refs")
    rows = []
    for pid, start, end, parallel in cur.execute(
        "SELECT id, start_vid, end_vid, parallel FROM pericopes WHERE parallel IS NOT NULL"
    ).fetchall():
        for ref in parse_refs(parallel, limit=8):
            rows.append((start, ref.start, ref.end, 1, "bsb-parallel"))
    cur.executemany(
        "INSERT INTO cross_refs (from_vid, to_start, to_end, votes, source) VALUES (?,?,?,?,?)",
        rows,
    )
    conn.commit()
    log(f"  {len(rows)} cross-references")
    return len(rows)


# ---------------------------------------------------------------------------
# stage 5: contested passages
# ---------------------------------------------------------------------------


def build_contested(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    cur.execute("DELETE FROM contested_positions")
    cur.execute("DELETE FROM contested")
    n = 0
    for entry in CONTESTED:
        refs = parse_refs(entry["ref"], limit=1)
        if not refs:
            log(f"  ! could not resolve contested ref {entry['ref']!r}")
            continue
        r = refs[0]
        cur.execute(
            "INSERT INTO contested (start_vid, end_vid, ref, topic, question) VALUES (?,?,?,?,?)",
            (r.start, r.end, r.ref, entry["topic"], entry["question"]),
        )
        cid = cur.lastrowid
        cur.executemany(
            "INSERT INTO contested_positions (contested_id, tradition, position) VALUES (?,?,?)",
            [(cid, k, v) for k, v in entry["positions"].items()],
        )
        n += 1
    conn.commit()
    log(f"  {n} contested passages, "
        f"{cur.execute('SELECT COUNT(*) FROM contested_positions').fetchone()[0]} positions")
    return n


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the Bible corpus database.")
    ap.add_argument("--source-dir", required=True, help="directory of source XML files")
    ap.add_argument("--db", default=None, help="output database path")
    ap.add_argument("--only", nargs="*", help="limit to these translation abbreviations")
    ap.add_argument("--skip-embeddings", action="store_true")
    args = ap.parse_args(argv)

    src_dir = Path(args.source_dir)
    if not src_dir.is_dir():
        log(f"source directory not found: {src_dir}")
        return 1

    conn = connect(args.db)
    init(conn)

    t0 = time.time()
    log("verses")
    ref_headings: list[ParsedHeading] = []
    wanted = set(args.only) if args.only else None

    for src in SOURCES:
        if wanted and src.abbrev not in wanted:
            continue
        path = src_dir / src.filename
        if not path.exists():
            log(f"  {src.abbrev:7} SKIPPED — {src.filename} not found")
            continue
        try:
            _, headings = ingest_translation(conn, src, path)
            if src.abbrev == REFERENCE:
                ref_headings = headings
        except Exception as exc:  # keep going; one bad file should not kill the build
            log(f"  {src.abbrev:7} FAILED — {type(exc).__name__}: {exc}")

    if ref_headings:
        log("pericopes")
        build_pericopes(conn, ref_headings)
    else:
        log("pericopes  SKIPPED — reference translation not ingested")

    log("lexical index")
    build_fts(conn)
    log("cross-references")
    build_crossrefs(conn)
    log("contested passages")
    build_contested(conn)

    if not args.skip_embeddings:
        log("embeddings")
        from ..retrieval.embed import build_index
        build_index(conn)

    total = conn.execute("SELECT COUNT(*) FROM verses").fetchone()[0]
    log(f"\ndone in {time.time() - t0:.1f}s — {total:,} verse records")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
