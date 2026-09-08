"""Canonical book metadata for the 66-book Protestant canon.

This module is the single source of truth for book identity across the whole
system. Every ingested translation, however it names its books, is normalized
to an OSIS id here (Gen, 1Cor, Rev...). Reference parsing, storage, retrieval
and citation all speak OSIS.

Genre matters downstream: the model is told what kind of literature a passage
is, because you do not read Psalms the way you read Romans, and a system that
flattens that distinction gives bad answers.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Book:
    osis: str
    name: str
    testament: str  # "OT" | "NT"
    order: int
    genre: str
    chapters: int
    usfx: str  # 3-letter USFX / Paratext code
    aliases: tuple[str, ...] = field(default=())


# genre buckets used in prompt construction
GENRES = {
    "law": "Torah / Pentateuch — narrative and covenant law",
    "history": "Historical narrative",
    "wisdom": "Wisdom literature",
    "poetry": "Hebrew poetry",
    "prophecy": "Prophetic literature",
    "gospel": "Gospel — theological biography",
    "acts": "Historical narrative of the early church",
    "epistle": "Occasional letter to a specific audience",
    "apocalyptic": "Apocalyptic literature",
}

BOOKS: list[Book] = [
    Book("Gen", "Genesis", "OT", 1, "law", 50, "GEN", ("gen", "ge", "gn")),
    Book("Exod", "Exodus", "OT", 2, "law", 40, "EXO", ("exod", "ex", "exo")),
    Book("Lev", "Leviticus", "OT", 3, "law", 27, "LEV", ("lev", "le", "lv")),
    Book("Num", "Numbers", "OT", 4, "law", 36, "NUM", ("num", "nu", "nm", "nb")),
    Book("Deut", "Deuteronomy", "OT", 5, "law", 34, "DEU", ("deut", "dt", "de")),
    Book("Josh", "Joshua", "OT", 6, "history", 24, "JOS", ("josh", "jos", "jsh")),
    Book("Judg", "Judges", "OT", 7, "history", 21, "JDG", ("judg", "jdg", "jg")),
    Book("Ruth", "Ruth", "OT", 8, "history", 4, "RUT", ("ruth", "rth", "ru")),
    Book("1Sam", "1 Samuel", "OT", 9, "history", 31, "1SA", ("1sam", "1sa", "1s", "1samuel", "firstsamuel")),
    Book("2Sam", "2 Samuel", "OT", 10, "history", 24, "2SA", ("2sam", "2sa", "2s", "2samuel", "secondsamuel")),
    Book("1Kgs", "1 Kings", "OT", 11, "history", 22, "1KI", ("1kgs", "1ki", "1k", "1kings", "firstkings")),
    Book("2Kgs", "2 Kings", "OT", 12, "history", 25, "2KI", ("2kgs", "2ki", "2k", "2kings", "secondkings")),
    Book("1Chr", "1 Chronicles", "OT", 13, "history", 29, "1CH", ("1chr", "1ch", "1chron", "1chronicles")),
    Book("2Chr", "2 Chronicles", "OT", 14, "history", 36, "2CH", ("2chr", "2ch", "2chron", "2chronicles")),
    Book("Ezra", "Ezra", "OT", 15, "history", 10, "EZR", ("ezra", "ezr")),
    Book("Neh", "Nehemiah", "OT", 16, "history", 13, "NEH", ("neh", "ne")),
    Book("Esth", "Esther", "OT", 17, "history", 10, "EST", ("esth", "est", "es")),
    Book("Job", "Job", "OT", 18, "wisdom", 42, "JOB", ("job", "jb")),
    Book("Ps", "Psalms", "OT", 19, "poetry", 150, "PSA", ("ps", "psa", "psalm", "psalms", "pss")),
    Book("Prov", "Proverbs", "OT", 20, "wisdom", 31, "PRO", ("prov", "pro", "pr", "prv")),
    Book("Eccl", "Ecclesiastes", "OT", 21, "wisdom", 12, "ECC", ("eccl", "ecc", "ec", "qoh", "qoheleth")),
    Book("Song", "Song of Solomon", "OT", 22, "poetry", 8, "SNG",
         ("song", "sng", "sos", "songofsolomon", "songofsongs", "canticles", "cant")),
    Book("Isa", "Isaiah", "OT", 23, "prophecy", 66, "ISA", ("isa", "is")),
    Book("Jer", "Jeremiah", "OT", 24, "prophecy", 52, "JER", ("jer", "je", "jr")),
    Book("Lam", "Lamentations", "OT", 25, "poetry", 5, "LAM", ("lam", "la")),
    Book("Ezek", "Ezekiel", "OT", 26, "prophecy", 48, "EZK", ("ezek", "eze", "ezk", "ez")),
    Book("Dan", "Daniel", "OT", 27, "apocalyptic", 12, "DAN", ("dan", "da", "dn")),
    Book("Hos", "Hosea", "OT", 28, "prophecy", 14, "HOS", ("hos", "ho")),
    Book("Joel", "Joel", "OT", 29, "prophecy", 3, "JOL", ("joel", "jol", "jl")),
    Book("Amos", "Amos", "OT", 30, "prophecy", 9, "AMO", ("amos", "amo", "am")),
    Book("Obad", "Obadiah", "OT", 31, "prophecy", 1, "OBA", ("obad", "oba", "ob")),
    Book("Jonah", "Jonah", "OT", 32, "prophecy", 4, "JON", ("jonah", "jon", "jnh")),
    Book("Mic", "Micah", "OT", 33, "prophecy", 7, "MIC", ("mic", "mi")),
    Book("Nah", "Nahum", "OT", 34, "prophecy", 3, "NAM", ("nah", "na", "nam")),
    Book("Hab", "Habakkuk", "OT", 35, "prophecy", 3, "HAB", ("hab", "hb")),
    Book("Zeph", "Zephaniah", "OT", 36, "prophecy", 3, "ZEP", ("zeph", "zep", "zp")),
    Book("Hag", "Haggai", "OT", 37, "prophecy", 2, "HAG", ("hag", "hg")),
    Book("Zech", "Zechariah", "OT", 38, "prophecy", 14, "ZEC", ("zech", "zec", "zc")),
    Book("Mal", "Malachi", "OT", 39, "prophecy", 4, "MAL", ("mal", "ml")),
    Book("Matt", "Matthew", "NT", 40, "gospel", 28, "MAT", ("matt", "mat", "mt")),
    Book("Mark", "Mark", "NT", 41, "gospel", 16, "MRK", ("mark", "mrk", "mk", "mr")),
    Book("Luke", "Luke", "NT", 42, "gospel", 24, "LUK", ("luke", "luk", "lk")),
    Book("John", "John", "NT", 43, "gospel", 21, "JHN", ("john", "jhn", "jn", "joh")),
    Book("Acts", "Acts", "NT", 44, "acts", 28, "ACT", ("acts", "act", "ac")),
    Book("Rom", "Romans", "NT", 45, "epistle", 16, "ROM", ("rom", "ro", "rm")),
    Book("1Cor", "1 Corinthians", "NT", 46, "epistle", 16, "1CO", ("1cor", "1co", "1c", "1corinthians", "firstcorinthians")),
    Book("2Cor", "2 Corinthians", "NT", 47, "epistle", 13, "2CO", ("2cor", "2co", "2c", "2corinthians", "secondcorinthians")),
    Book("Gal", "Galatians", "NT", 48, "epistle", 6, "GAL", ("gal", "ga")),
    Book("Eph", "Ephesians", "NT", 49, "epistle", 6, "EPH", ("eph", "ep")),
    Book("Phil", "Philippians", "NT", 50, "epistle", 4, "PHP", ("phil", "php", "pp", "philippians")),
    Book("Col", "Colossians", "NT", 51, "epistle", 4, "COL", ("col", "cl")),
    Book("1Thess", "1 Thessalonians", "NT", 52, "epistle", 5, "1TH", ("1thess", "1th", "1thes", "1thessalonians")),
    Book("2Thess", "2 Thessalonians", "NT", 53, "epistle", 3, "2TH", ("2thess", "2th", "2thes", "2thessalonians")),
    Book("1Tim", "1 Timothy", "NT", 54, "epistle", 6, "1TI", ("1tim", "1ti", "1timothy", "firsttimothy")),
    Book("2Tim", "2 Timothy", "NT", 55, "epistle", 4, "2TI", ("2tim", "2ti", "2timothy", "secondtimothy")),
    Book("Titus", "Titus", "NT", 56, "epistle", 3, "TIT", ("titus", "tit", "ti")),
    Book("Phlm", "Philemon", "NT", 57, "epistle", 1, "PHM", ("phlm", "phm", "philem", "philemon")),
    Book("Heb", "Hebrews", "NT", 58, "epistle", 13, "HEB", ("heb", "hb")),
    Book("Jas", "James", "NT", 59, "epistle", 5, "JAS", ("jas", "jam", "james", "jm")),
    Book("1Pet", "1 Peter", "NT", 60, "epistle", 5, "1PE", ("1pet", "1pe", "1p", "1peter", "firstpeter")),
    Book("2Pet", "2 Peter", "NT", 61, "epistle", 3, "2PE", ("2pet", "2pe", "2p", "2peter", "secondpeter")),
    Book("1John", "1 John", "NT", 62, "epistle", 5, "1JN", ("1john", "1jn", "1jo", "1j", "firstjohn")),
    Book("2John", "2 John", "NT", 63, "epistle", 1, "2JN", ("2john", "2jn", "2jo", "2j", "secondjohn")),
    Book("3John", "3 John", "NT", 64, "epistle", 1, "3JN", ("3john", "3jn", "3jo", "3j", "thirdjohn")),
    Book("Jude", "Jude", "NT", 65, "epistle", 1, "JUD", ("jude", "jud", "jd")),
    Book("Rev", "Revelation", "NT", 66, "apocalyptic", 22, "REV",
         ("rev", "re", "rv", "revelation", "apocalypse", "revelations")),
]

BY_OSIS: dict[str, Book] = {b.osis: b for b in BOOKS}
BY_USFX: dict[str, Book] = {b.usfx: b for b in BOOKS}


def _norm(s: str) -> str:
    """Aggressively normalize a book token for lookup."""
    s = s.strip().lower().replace(".", "").replace("_", " ")
    # spell out leading ordinals: "first john" / "1st john" / "i john" -> "1john"
    s = s.replace("first ", "1").replace("second ", "2").replace("third ", "3")
    s = s.replace("1st ", "1").replace("2nd ", "2").replace("3rd ", "3")
    # roman numeral prefixes, only when followed by a letter run
    for roman, digit in (("iii ", "3"), ("ii ", "2"), ("i ", "1")):
        if s.startswith(roman):
            s = digit + s[len(roman):]
            break
    return "".join(s.split())


# Lookup table: normalized token -> OSIS id. Built from names, OSIS ids,
# USFX codes and hand-listed aliases.
_LOOKUP: dict[str, str] = {}
for _b in BOOKS:
    for key in (_b.osis, _b.name, _b.usfx, *_b.aliases):
        _LOOKUP[_norm(key)] = _b.osis
    # also the space-free full name, e.g. "songofsolomon"
    _LOOKUP[_norm(_b.name)] = _b.osis


def resolve_book(token: str) -> str | None:
    """Resolve any reasonable spelling of a book name to its OSIS id."""
    if not token:
        return None
    key = _norm(token)
    if key in _LOOKUP:
        return _LOOKUP[key]
    # unique-prefix fallback: "philipp" -> Phil, but "j" stays ambiguous
    if len(key) >= 3:
        hits = {v for k, v in _LOOKUP.items() if k.startswith(key)}
        if len(hits) == 1:
            return hits.pop()
    return None


def book(osis: str) -> Book | None:
    return BY_OSIS.get(osis)


def from_usfx(code: str) -> Book | None:
    return BY_USFX.get(code.strip().upper())


# Total verse count of the Protestant canon, used as an ingestion sanity check.
# (KJV versification; translations differ by a handful of verses.)
KJV_TOTAL_VERSES = 31102
