"""Scripture reference parsing.

Most real questions about the Bible contain an explicit reference ("what does
Romans 8:28 actually mean?"), and for those, vector search is the wrong tool —
you want a deterministic lookup. This module turns free text into exact verse
spans so the retrieval layer can anchor on them before falling back to search.

Handles the shapes people actually type:

    John 3:16              Jn 3.16            1 Cor 13:4-7
    John 3:16-18           Rom 8:28–30        Gen 1:1-2:3
    Psalm 23               Ps 119:105         Matt 5:3,5,9
    1 John 4:8             II Timothy 3:16    Revelation 21
    "Rom 8:28; Eph 1:4"    Song 2:1           3 Jn 4
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..canon import BY_OSIS, BOOKS, resolve_book
from ..db import range_str, vid

# ---------------------------------------------------------------------------
# book-name matching
# ---------------------------------------------------------------------------

# Build one alternation of every spelling we accept, longest first so
# "1 Corinthians" wins over "1 Cor" and "Song of Solomon" over "Song".
_variants: set[str] = set()
for _b in BOOKS:
    _variants.add(_b.name)
    _variants.add(_b.osis)
    for _a in _b.aliases:
        _variants.add(_a)

# ordinal prefixes people actually write
_ORDINALS = {
    "1": ["1", "1st", "first", "i"],
    "2": ["2", "2nd", "second", "ii"],
    "3": ["3", "3rd", "third", "iii"],
}

_expanded: set[str] = set()
for _v in _variants:
    _expanded.add(_v)
    m = re.match(r"^([123])\s*(.+)$", _v)
    if m:
        num, rest = m.groups()
        for pre in _ORDINALS[num]:
            _expanded.add(f"{pre} {rest}")
            _expanded.add(f"{pre}{rest}")

_BOOK_ALT = "|".join(
    re.escape(v) for v in sorted(_expanded, key=len, reverse=True)
)

# book, then the numeric tail: chapter[:verse][-end][,more]
# ':' and '.' are both accepted as the chapter/verse separator ("Jn 3.16"),
# but only when a digit follows, so a sentence-ending "Genesis 1." is safe.
_REF_RE = re.compile(
    rf"\b(?P<book>{_BOOK_ALT})\.?\s*"
    r"(?P<tail>\d{1,3}\s*(?:[:.]\s*\d{1,3})?"
    r"(?:\s*[-–—]\s*\d{1,3}(?:\s*[:.]\s*\d{1,3})?)?"
    r"(?:\s*,\s*\d{1,3}(?:\s*[:.]\s*\d{1,3})?(?:\s*[-–—]\s*\d{1,3})?)*)?",
    re.IGNORECASE,
)

_DASH = re.compile(r"[-–—]")


@dataclass(frozen=True)
class Ref:
    start: int  # vid
    end: int  # vid, inclusive
    book: str
    ref: str  # normalized display form
    raw: str  # what was matched in the source text

    @property
    def is_chapter(self) -> bool:
        return self.start % 1000 == 1 and self.end % 1000 >= 100


def _last_verse(book: str, chapter: int) -> int:
    """Upper bound for a chapter. We do not ship a versification table, so we
    use 200 (above the 176-verse maximum, Psalm 119) and let the range query
    clip to whatever verses actually exist."""
    return 200


def _clip(book: str, chapter: int) -> int:
    b = BY_OSIS.get(book)
    if b and chapter > b.chapters:
        return b.chapters
    return chapter


def parse_refs(text: str, limit: int = 12) -> list[Ref]:
    """Extract every scripture reference in `text`, in order of appearance."""
    out: list[Ref] = []
    seen: set[tuple[int, int]] = set()

    for m in _REF_RE.finditer(text or ""):
        book = resolve_book(m.group("book"))
        if not book:
            continue
        tail = (m.group("tail") or "").strip()
        raw = m.group(0).strip()

        if not tail:
            # bare book name — only useful as a weak signal, and far too noisy
            # to treat as a reference ("job", "acts", "mark" are common words).
            continue

        for start, end in _expand_tail(book, tail):
            key = (start, end)
            if key in seen:
                continue
            seen.add(key)
            out.append(Ref(start, end, book, range_str(start, end), raw))
            if len(out) >= limit:
                return out
    return out


def _expand_tail(book: str, tail: str) -> list[tuple[int, int]]:
    """Turn '3:16-18' or '1:1-2:3' or '5:3,5,9' into concrete vid spans."""
    spans: list[tuple[int, int]] = []
    tail = re.sub(r"\s+", "", tail).replace(".", ":")

    # split top-level comma list, remembering the governing chapter
    chapter_ctx: int | None = None

    # In a one-chapter book (Obadiah, Philemon, 2-3 John, Jude) a bare number
    # is a verse, not a chapter: "3 Jn 4" means 3 John 1:4.
    b = BY_OSIS.get(book)
    single_chapter = bool(b and b.chapters == 1)
    if single_chapter:
        chapter_ctx = 1

    for part in tail.split(","):
        if not part:
            continue
        pieces = _DASH.split(part, maxsplit=1)
        left = pieces[0]
        right = pieces[1] if len(pieces) > 1 else None

        # ---- left side
        if ":" in left:
            c_s, v_s = left.split(":", 1)
            try:
                ch, vs = int(c_s), int(v_s)
            except ValueError:
                continue
            chapter_ctx = ch
        else:
            try:
                n = int(left)
            except ValueError:
                continue
            if chapter_ctx is None:
                ch, vs = n, None  # whole chapter
                chapter_ctx = ch
            else:
                ch, vs = chapter_ctx, n  # continuing a verse list

        ch = _clip(book, ch)
        start = vid(book, ch, vs if vs is not None else 1)

        # ---- right side
        if right is None:
            end = start if vs is not None else vid(book, ch, _last_verse(book, ch))
        elif ":" in right:
            c_e, v_e = right.split(":", 1)
            try:
                ch2, vs2 = _clip(book, int(c_e)), int(v_e)
            except ValueError:
                continue
            end = vid(book, ch2, vs2)
        else:
            try:
                n = int(right)
            except ValueError:
                continue
            if vs is None:
                # chapter range: "Gen 1-3"
                end = vid(book, _clip(book, n), _last_verse(book, n))
            else:
                end = vid(book, ch, n)

        if end < start:
            start, end = end, start
        spans.append((start, end))

    return spans


def parse_one(text: str) -> Ref | None:
    """Parse a single reference, e.g. from a URL path or a search box."""
    refs = parse_refs(text, limit=1)
    return refs[0] if refs else None


def looks_like_reference(text: str) -> bool:
    """True when the whole input is essentially just a reference, meaning the
    user wants to *read* a passage rather than ask a question about it."""
    t = (text or "").strip()
    if not t or len(t) > 60:
        return False
    refs = parse_refs(t, limit=2)
    if not refs:
        return False
    # how much of the string did the reference(s) account for?
    covered = sum(len(r.raw) for r in refs)
    return covered >= max(3, int(len(t) * 0.7))
