"""Registry of ingestable translations.

Every entry here is public domain or openly licensed. Nothing in this file
requires a publisher agreement, which is the whole point: the corpus can be
redistributed, indexed, and served without legal exposure.

`philosophy` places each translation on the formal-equivalence ("word for
word") to dynamic-equivalence ("thought for thought") axis. This is surfaced
to the reader, because a large share of apparent contradictions between
translations are just different points on that axis.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    abbrev: str
    name: str
    filename: str
    fmt: str
    year: str
    license: str
    philosophy: str
    tradition: str
    notes: str
    sort_order: int
    language: str = "en"
    is_reference: bool = False


SOURCES: list[Source] = [
    Source(
        "BSB", "Berean Standard Bible", "eng-bsb.usfx.xml", "usfx", "2022",
        "Public Domain",
        "Optimal equivalence — balances literal accuracy with readable modern English",
        "Interconfessional, translated from Hebrew and Greek",
        "Modern, freely licensed, translated directly from the original languages. "
        "Used as this system's reference text for passage segmentation and search "
        "because it is both modern and unencumbered.",
        sort_order=1, is_reference=True,
    ),
    Source(
        "WEB", "World English Bible", "eng-web.usfx.xml", "usfx", "2000",
        "Public Domain",
        "Formal equivalence — a modern-English update of the ASV",
        "Protestant, Majority Text influenced",
        "A public-domain modernization of the American Standard Version.",
        sort_order=2,
    ),
    Source(
        "KJV", "King James Version", "eng-kjv.osis.xml", "osis", "1611/1769",
        "Public Domain",
        "Formal equivalence — Jacobean English",
        "Anglican; Textus Receptus base text",
        "The most historically influential English Bible. Its base Greek text "
        "differs from modern critical editions, which explains most places where "
        "it includes verses other translations footnote or omit.",
        sort_order=3, is_reference=True,
    ),
    Source(
        "ASV", "American Standard Version", "eng-asv.zefania.xml", "zefania", "1901",
        "Public Domain",
        "Formal equivalence — highly literal, often stilted",
        "Protestant, ecumenical revision committee",
        "Prized for accuracy over style; the base for many later translations.",
        sort_order=4,
    ),
    Source(
        "YLT", "Young's Literal Translation", "eng-ylt.zefania.xml", "zefania", "1862/1898",
        "Public Domain",
        "Extreme formal equivalence — preserves Hebrew and Greek tense and word order",
        "Protestant",
        "Deliberately awkward English in order to expose the grammar of the "
        "original. Useful for seeing verb aspect that smoother translations hide. "
        "This edition covers the New Testament only.",
        sort_order=5,
    ),
    Source(
        "DARBY", "Darby Translation", "eng-darby.zefania.xml", "zefania", "1890",
        "Public Domain",
        "Formal equivalence — technical and precise",
        "Plymouth Brethren",
        "A scholarly literal translation by J. N. Darby, attentive to critical texts.",
        sort_order=6,
    ),
    Source(
        "DRA", "Douay-Rheims (1899 American Edition)", "eng-dra.zefania.xml", "zefania", "1899",
        "Public Domain",
        "Formal equivalence — translated from the Latin Vulgate",
        "Roman Catholic",
        "The historic English Catholic Bible. Because it renders the Vulgate "
        "rather than Hebrew and Greek, its wording sometimes reflects Jerome's "
        "Latin choices. Deuterocanonical books are outside this system's 66-book scope.",
        sort_order=7,
    ),
    Source(
        "BBE", "Bible in Basic English", "eng-bbe.usfx.xml", "usfx", "1949",
        "Public Domain",
        "Dynamic equivalence — restricted to a ~1,000-word core vocabulary",
        "Protestant",
        "Written for readers with limited English. The constrained vocabulary "
        "makes it unusually clear, at the cost of theological precision.",
        sort_order=8,
    ),
    Source(
        "WEBBE", "World English Bible (British Edition)", "eng-gb-webbe.usfx.xml", "usfx", "2000",
        "Public Domain",
        "Formal equivalence — WEB with British spelling and idiom",
        "Protestant",
        "Identical translation to the WEB with anglicized spelling.",
        sort_order=9,
    ),
    Source(
        "OEB-US", "Open English Bible (US Edition)", "eng-us-oeb.osis.xml", "osis", "2010-",
        "Public Domain (CC0)",
        "Dynamic equivalence — contemporary, readable English",
        "Ecumenical, crowd-reviewed",
        "An in-progress modern translation. Coverage is incomplete; unfinished "
        "books are simply absent rather than partial.",
        sort_order=10,
    ),
    Source(
        "OEB-CW", "Open English Bible (Commonwealth Edition)", "eng-gb-oeb.osis.xml", "osis", "2010-",
        "Public Domain (CC0)",
        "Dynamic equivalence — contemporary English, Commonwealth spelling",
        "Ecumenical, crowd-reviewed",
        "As OEB-US, with Commonwealth spelling. Coverage is incomplete.",
        sort_order=11,
    ),
    Source(
        "VUL", "Clementine Vulgate", "lat-clementine.usfx.xml", "usfx", "1592",
        "Public Domain",
        "Latin — Jerome's translation as standardized by Clement VIII",
        "Roman Catholic",
        "The Latin text that shaped Western theological vocabulary for a "
        "millennium and underlies the Douay-Rheims.",
        sort_order=50, language="la",
    ),
]

BY_ABBREV = {s.abbrev: s for s in SOURCES}

# Translations whose text is added to the lexical index. Indexing all of them
# would make eleven near-identical wordings of the same verse compete for the
# same result slots, burying genuinely different passages. One modern and one
# traditional text covers how people actually phrase searches.
INDEXED = ("BSB", "KJV")

# The text used for pericope segmentation and dense retrieval.
REFERENCE = "BSB"
