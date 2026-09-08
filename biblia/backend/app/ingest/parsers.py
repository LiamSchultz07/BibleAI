"""Parsers for the three XML Bible formats we ingest: OSIS, USFX and Zefania.

All three use *milestone* or *container* verse markup and all three are
inconsistent in the wild, so each parser walks the tree in document order and
accumulates character data between verse boundaries rather than trusting
element nesting.

Every parser yields `ParsedVerse` records keyed by OSIS book id, so downstream
code never has to know which format a translation came from.

USFX additionally carries editorial section headings (`<s>`) and parallel-passage
notes (`<p sfm="r">`). Those are the backbone of pericope segmentation, so
`parse_usfx` emits them as `ParsedHeading` records interleaved with verses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

from lxml import etree

from ..canon import from_usfx, resolve_book

# ---------------------------------------------------------------------------
# records
# ---------------------------------------------------------------------------


@dataclass
class ParsedVerse:
    book: str  # OSIS id
    chapter: int
    verse: int
    text: str


@dataclass
class ParsedHeading:
    book: str
    chapter: int
    after_verse: int  # heading appears immediately before this verse number
    level: int
    title: str
    parallel: str | None = None  # e.g. "(John 1:1-5; Hebrews 11:1-3)"


_WS = re.compile(r"\s+")
# Editorial/apparatus elements whose character data must never enter verse text.
_SKIP_TAGS = {
    "note", "f", "fe", "x", "ef", "ex",  # footnotes / cross-ref apparatus
    "rem", "toc", "h", "id", "ide",      # metadata
    "cl", "cp", "va", "vp",              # alternate chapter/verse labels
    "fig", "ndx", "milestone",
}


def _clean(s: str) -> str:
    s = _WS.sub(" ", s).strip()
    # collapse space before closing punctuation introduced by markup removal
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    return s


def _localname(tag) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _read(path: str):
    """Parse a source file, tolerating truncation.

    Several of these files are published with a missing closing tag or a
    truncated final book. Recovery mode salvages everything up to the damage,
    which for a Bible file means losing a few trailing verses rather than the
    whole translation. Strict parsing is tried first so that clean files are
    never silently degraded.
    """
    try:
        return etree.parse(path).getroot()
    except etree.XMLSyntaxError:
        parser = etree.XMLParser(recover=True, huge_tree=True)
        root = etree.parse(path, parser).getroot()
        if root is None:
            raise
        return root


# ---------------------------------------------------------------------------
# OSIS
# ---------------------------------------------------------------------------


def parse_osis(path: str) -> Iterator[ParsedVerse | ParsedHeading]:
    """Parse an OSIS file.

    Verses are milestones: `<verse osisID="Gen.1.1" sID=.../>` opens and
    `<verse eID=.../>` closes. Some OSIS files instead nest the text inside the
    verse element; both shapes are handled by tracking an "open verse" and
    accumulating all text seen while it is open.
    """
    root = _read(path)

    cur: tuple[str, int, int] | None = None
    buf: list[str] = []
    skip_depth = 0

    def flush() -> ParsedVerse | None:
        nonlocal cur, buf
        if cur is None:
            return None
        text = _clean("".join(buf))
        out = ParsedVerse(cur[0], cur[1], cur[2], text) if text else None
        cur, buf = None, []
        return out

    for event, el in etree.iterwalk(root, events=("start", "end")):
        tag = _localname(el.tag)

        if event == "start":
            if tag in _SKIP_TAGS:
                skip_depth += 1
                continue
            if skip_depth:
                continue

            if tag == "verse":
                osis_id = el.get("osisID")
                if osis_id:  # opening milestone (or container)
                    v = flush()
                    if v:
                        yield v
                    # osisID can be a range or space-separated list: take the first
                    first = osis_id.split()[0].split("-")[0]
                    parts = first.split(".")
                    if len(parts) == 3:
                        bk = resolve_book(parts[0])
                        if bk:
                            try:
                                cur = (bk, int(parts[1]), int(parts[2]))
                                buf = []
                            except ValueError:
                                cur = None
                elif el.get("eID"):  # closing milestone
                    v = flush()
                    if v:
                        yield v
            elif tag == "title" and cur is None:
                # section headings between verses; skip main book titles
                if el.get("type") in (None, "section", "sub") and el.get("canonical") != "true":
                    pass  # headings in OSIS are unreliable; USFX supplies ours
            else:
                if cur is not None and el.text:
                    buf.append(el.text)

        else:  # end
            if tag in _SKIP_TAGS:
                skip_depth = max(0, skip_depth - 1)
                if not skip_depth and cur is not None and el.tail:
                    buf.append(el.tail)
                continue
            if skip_depth:
                continue
            if cur is not None and el.tail:
                buf.append(el.tail)

    v = flush()
    if v:
        yield v


# ---------------------------------------------------------------------------
# USFX
# ---------------------------------------------------------------------------


def parse_usfx(path: str) -> Iterator[ParsedVerse | ParsedHeading]:
    """Parse a USFX file.

    Structure: `<book id="GEN">` … `<c id="1"/>` … `<v id="1" bcv="GEN.1.1"/>`
    text `<ve/>`. Section headings arrive as `<s level="1">Title</s>` and the
    parallel-passage line as `<p sfm="r">(John 1:1-5)</p>`.
    """
    root = _read(path)

    book: str | None = None
    chapter = 0
    cur: tuple[str, int, int] | None = None
    buf: list[str] = []
    skip_depth = 0
    pending_heading: ParsedHeading | None = None
    # heading text accumulates across children of <s>
    in_s = 0
    s_buf: list[str] = []
    s_level = 1
    in_r = 0
    r_buf: list[str] = []
    next_verse_guess = 1

    def flush() -> ParsedVerse | None:
        nonlocal cur, buf
        if cur is None:
            return None
        text = _clean("".join(buf))
        out = ParsedVerse(cur[0], cur[1], cur[2], text) if text else None
        cur, buf = None, []
        return out

    for event, el in etree.iterwalk(root, events=("start", "end")):
        tag = _localname(el.tag)

        if event == "start":
            if tag in _SKIP_TAGS:
                skip_depth += 1
                continue
            if skip_depth:
                continue

            if tag == "book":
                v = flush()
                if v:
                    yield v
                b = from_usfx(el.get("id", ""))
                book = b.osis if b else None
                chapter = 0
                next_verse_guess = 1

            elif tag == "c":
                v = flush()
                if v:
                    yield v
                try:
                    chapter = int(el.get("id", "0"))
                except ValueError:
                    chapter = 0
                next_verse_guess = 1

            elif tag == "v":
                v = flush()
                if v:
                    yield v
                bcv = el.get("bcv")
                num = None
                bk, ch = book, chapter
                if bcv:
                    parts = bcv.split(".")
                    if len(parts) == 3:
                        b2 = from_usfx(parts[0])
                        if b2:
                            bk = b2.osis
                        try:
                            ch, num = int(parts[1]), int(re.sub(r"\D.*$", "", parts[2]) or 0)
                        except ValueError:
                            num = None
                if num is None:
                    raw = el.get("id", "")
                    m = re.match(r"(\d+)", raw)
                    num = int(m.group(1)) if m else next_verse_guess
                if bk and ch and num:
                    cur = (bk, ch, num)
                    buf = []
                    next_verse_guess = num + 1
                    if pending_heading is not None:
                        pending_heading.after_verse = num
                        pending_heading.book = bk
                        pending_heading.chapter = ch
                        yield pending_heading
                        pending_heading = None

            elif tag == "s":
                v = flush()
                if v:
                    yield v
                in_s += 1
                s_buf = []
                try:
                    s_level = int(el.get("level") or (el.get("style", "s1")[-1]))
                except (ValueError, IndexError):
                    s_level = 1
                if el.text:
                    s_buf.append(el.text)

            elif tag == "p" and el.get("sfm") == "r":
                in_r += 1
                r_buf = []
                if el.text:
                    r_buf.append(el.text)

            else:
                if in_s and el.text:
                    s_buf.append(el.text)
                elif in_r and el.text:
                    r_buf.append(el.text)
                elif cur is not None and el.text:
                    buf.append(el.text)

        else:  # end
            if tag in _SKIP_TAGS:
                skip_depth = max(0, skip_depth - 1)
                if not skip_depth and cur is not None and el.tail:
                    buf.append(el.tail)
                continue
            if skip_depth:
                continue

            if tag == "ve":
                v = flush()
                if v:
                    yield v

            elif tag == "s":
                in_s = max(0, in_s - 1)
                if not in_s:
                    title = _clean("".join(s_buf))
                    if title and book:
                        pending_heading = ParsedHeading(
                            book=book, chapter=chapter, after_verse=next_verse_guess,
                            level=s_level, title=title,
                        )
                    s_buf = []

            elif tag == "p" and el.get("sfm") == "r":
                in_r = max(0, in_r - 1)
                if not in_r:
                    par = _clean("".join(r_buf))
                    if par and pending_heading is not None:
                        pending_heading.parallel = par
                    r_buf = []

            if in_s and el.tail:
                s_buf.append(el.tail)
            elif in_r and el.tail:
                r_buf.append(el.tail)
            elif cur is not None and el.tail:
                buf.append(el.tail)

    v = flush()
    if v:
        yield v


# ---------------------------------------------------------------------------
# Zefania
# ---------------------------------------------------------------------------


def parse_zefania(path: str) -> Iterator[ParsedVerse | ParsedHeading]:
    """Parse a Zefania file: `<BIBLEBOOK bname=><CHAPTER cnumber=><VERS vnumber=>`.

    Verses are containers here, so we take the element's full text content
    minus any note children.
    """
    root = _read(path)

    for bb in root.iter():
        if _localname(bb.tag) != "BIBLEBOOK":
            continue
        bk = (
            resolve_book(bb.get("bname") or "")
            or resolve_book(bb.get("bsname") or "")
        )
        if not bk:
            # fall back to canonical order via bnumber
            try:
                n = int(bb.get("bnumber", "0"))
            except ValueError:
                n = 0
            from ..canon import BOOKS
            bk = next((b.osis for b in BOOKS if b.order == n), None)
        if not bk:
            continue

        for ch_el in bb:
            if _localname(ch_el.tag) != "CHAPTER":
                continue
            try:
                ch = int(ch_el.get("cnumber", "0"))
            except ValueError:
                continue

            for v_el in ch_el:
                if _localname(v_el.tag) != "VERS":
                    continue
                try:
                    vn = int(v_el.get("vnumber", "0"))
                except ValueError:
                    continue

                parts: list[str] = []
                if v_el.text:
                    parts.append(v_el.text)
                for child in v_el.iter():
                    if child is v_el:
                        continue
                    if _localname(child.tag).lower() in _SKIP_TAGS:
                        if child.tail:
                            parts.append(child.tail)
                        continue
                    if child.text:
                        parts.append(child.text)
                    if child.tail:
                        parts.append(child.tail)

                text = _clean("".join(parts))
                if text and ch and vn:
                    yield ParsedVerse(bk, ch, vn, text)


PARSERS = {
    "osis": parse_osis,
    "usfx": parse_usfx,
    "zefania": parse_zefania,
}


def parse(path: str, fmt: str) -> Iterator[ParsedVerse | ParsedHeading]:
    if fmt not in PARSERS:
        raise ValueError(f"unknown format {fmt!r}; expected one of {sorted(PARSERS)}")
    return PARSERS[fmt](path)
