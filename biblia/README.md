# Biblia

Conversational Bible study over 12 open-license translations. Ask about a
passage, compare how translations render it, see where interpretive traditions
genuinely disagree, keep your own notes and highlights, and have any of it read
aloud.

**macOS / Linux**

```
make all      # venv, dependencies, texts, corpus build — about 3 minutes
make serve    # http://localhost:8000
```

**Windows** (PowerShell — `make` is not available there)

```powershell
.\setup.ps1   # same three minutes
.\run.ps1     # http://localhost:8000
```

Needs Python 3.10+, Node 18+, and git:

```powershell
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install Git.Git
```

Everything installs into a project-local `.venv`, so nothing touches your
system Python. No API key is required to run it — see
[Configuration](#configuration).

---

## What this is

A retrieval system over a verse-indexed Bible corpus, plus a conversational
layer that is only allowed to speak from what retrieval returns.

It is deliberately **not** a fine-tuned model. Training a model on Bible text
teaches it to *recite* Scripture, which is the one thing you least want: a model
generating verse text from weights will produce fluent, plausible, subtly wrong
quotations, and a study tool that misquotes verses is worse than no tool. Here
the text comes from a database, verbatim, and the model reasons over it.

## Architecture

```
XML sources (OSIS / USFX / Zefania)
        │
        ▼
  ingest  ──────────────►  SQLite
        │                    verses          311,458 rows, 12 translations
        │                    pericopes         3,086 passage units
        │                    verses_fts        FTS5 / BM25
        │                    pericope_vectors  dense, one per passage
        │                    cross_refs        2,030 links
        │                    contested            31 disputes, 117 positions
        ▼
  retrieval  ──►  reference parser  ─┐
                  BM25 (lexical)     ├─► reciprocal rank fusion ─► evidence
                  vectors (semantic) ─┘
        ▼
  prompt assembly ──► LLM (streaming) ──► cited answer
```

### Three decisions that matter

**Embed passages, not verses, and only once.** Vectors are built per *pericope*
in a single reference translation. Embedding all 12 translations would put
twelve near-identical points in the space for every verse, so a query for "God
works things for good" would return the same passage twelve times and push
genuinely different passages off the list. Retrieval finds the passage; the
translation fan-out happens afterward, at read time. It is also ~100× cheaper to
build.

**References are anchors, not search results.** Most Bible questions name a
passage ("what does Romans 8:28 mean?"). That is a deterministic lookup, and a
vector search must never outrank it. The reference is parsed out, resolved
exactly, and the remaining words — *not* the whole message — go to search.
Leaving "Romans 8:28" in the search text makes BM25 rank every passage
containing the word "Romans", burying the actual topic under narratives about
Rome. That bug is easy to ship and hard to notice.

**Contested ground is data, not vibes.** 31 passages where traditions durably
disagree are stored with each position written as its own adherents would argue
it. When retrieval lands inside one of those spans, the prompt is required to
present the range and attribute each reading. A general instruction to "be
balanced" does not work, because the model does not otherwise know *which*
passages are contested or who holds what.

### Verse identity

Every verse has an integer id:

```
vid = book_order × 1,000,000 + chapter × 1,000 + verse
```

Monotonic in canonical order, so passage ranges, context windows and
cross-reference spans are integer `BETWEEN` queries instead of three-column
comparisons.

## The corpus

Everything is public domain or openly licensed — no publisher agreement, no
legal exposure, fully redistributable.

| | Translation | Year | Approach |
|---|---|---|---|
| BSB | Berean Standard Bible | 2022 | optimal equivalence — the reference text |
| WEB | World English Bible | 2000 | formal, modern |
| KJV | King James Version | 1611/1769 | formal, Textus Receptus |
| ASV | American Standard Version | 1901 | formal, very literal |
| YLT | Young's Literal Translation | 1898 | extreme literal (NT only) |
| DARBY | Darby Translation | 1890 | formal, technical |
| DRA | Douay-Rheims American | 1899 | formal, from the Vulgate (Catholic) |
| BBE | Bible in Basic English | 1949 | ~1,000-word vocabulary |
| WEBBE | World English Bible (British) | 2000 | formal, modern |
| OEB-US / OEB-CW | Open English Bible | 2010– | dynamic (incomplete) |
| VUL | Clementine Vulgate | 1592 | Latin |

**What is deliberately absent:** NIV, ESV, NASB, NLT, CSB and every other modern
commercial translation. These cannot be ingested or redistributed without paid
licensing from Biblica, Crossway, or Lockman, and publishers are currently
reluctant to license full text to AI products. The schema carries a per-
translation licence field so licensed texts can be added later without a
migration.

## API

| | |
|---|---|
| `GET /api/health` | service and corpus status |
| `GET /api/translations` | translations with licence and philosophy |
| `GET /api/books` | canon metadata |
| `GET /api/passage?ref=&translation=&compare=` | read a passage |
| `GET /api/chapter/{book}/{chapter}` | read a chapter |
| `GET /api/search?q=&k=` | hybrid search |
| `GET /api/contested?ref=` | disputes touching a passage |
| `POST /api/chat` | streaming conversation (SSE) |
| `GET /api/session/{id}` | conversation history |
| `POST /api/auth/register` · `/login` · `GET /auth/me` | accounts |
| `PATCH /api/settings` | notes privacy, narrator voice and speed |
| `GET POST PATCH DELETE /api/notes` | notes anchored to verse spans |
| `GET POST DELETE /api/highlights` | verse highlighting |
| `GET POST /api/bookmarks` · `/api/history` | bookmarks, reading history |
| `GET /api/conversations` | saved conversations |

```bash
curl "localhost:8000/api/passage?ref=Romans+8:28&translation=BSB&compare=KJV"
```

## Profiles

An account adds notes, highlights, bookmarks, reading history and saved
conversations. Everything else — reading, searching, comparing translations,
asking questions — works signed out, so the personal layer is strictly
additive and no route requires auth to read scripture.

Passwords use `hashlib.scrypt` from the standard library (n=2¹⁵, ~50 ms per
verification) rather than a bcrypt or argon2 binding, so there is no native
dependency to install or keep patched. Sessions are JWTs.

Notes are anchored to **verse spans**, not pericope ids, so a note survives any
future re-segmentation of the corpus, and a note on Romans 8:28-30 surfaces when
you open Romans 8:29.

### Can the assistant read your notes?

A per-account setting with three modes, defaulting to **on request**:

| Mode | Behaviour |
|---|---|
| `never` | Notes are a reading feature and never enter a prompt. |
| `on_request` *(default)* | Included only when you ask — "what did I write here?" |
| `always` | Included whenever you study a passage you have written about. |

The default is deliberate. Notes on scripture frequently hold confessions,
prayers and doubts, and quietly shipping those to a model provider is not a
default worth choosing on someone's behalf. When notes are included, the reply
says so, and the system prompt instructs the model to treat them as the
reader's own thinking — not as instructions, and not as evidence for what a
passage means.

## Narrator

Browser-native narration over the Web Speech API: no key, no infrastructure, no
per-character cost, and it works offline.

Text is queued **one utterance per verse** rather than one per passage. The
obvious alternative — speak the whole chapter and track position with
`onboundary` character offsets — is unreliable, because some engines never fire
`onboundary` and those that do disagree on offsets. Per-verse utterances give
exact, portable verse-level highlighting from `onstart`/`onend` alone, and
sidestep the long-standing Chrome bug that stops synthesis after roughly 15
seconds of continuous speech.

Assistant replies can be narrated too. A cloud TTS provider would slot in behind
the same interface — `speak` would fetch and play audio per verse and nothing
above that line changes.

If a browser exposes the API but has no installed voice (common on Linux without
speech-dispatcher), the first utterance errors before starting; that case is
detected and reported rather than silently racing through the queue.

## Configuration

Nothing is required to boot. Corpus, lookup, search and comparison all work with
no keys; only conversation needs a model.

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | enables the conversational layer |
| `BIBLIA_LLM_MODEL` | `claude-sonnet-4-5` | chat model |
| `BIBLIA_EMBED_PROVIDER` | `lsa` | `lsa`, `voyage`, or `openai` |
| `VOYAGE_API_KEY` | — | for neural embeddings |
| `BIBLIA_DEFAULT_TRANSLATION` | `BSB` | |
| `BIBLIA_CORS` | `*` | allowed origins |
| `BIBLIA_SECRET_KEY` | *(ephemeral)* | signs session tokens — **must be set in production**, or every restart signs everyone out |

Without a key the chat endpoint streams the retrieval layer's raw output —
the exact evidence a model would receive. That makes retrieval quality
inspectable on its own, which is where most problems actually live.

### Embeddings

The default provider runs offline (TF-IDF reduced by SVD) so the system works
with no key and no model download. It handles thematic queries adequately but
misses vocabulary the corpus does not use — searching "communion" will not
find "the Lord's Supper". Setting `VOYAGE_API_KEY` and
`BIBLIA_EMBED_PROVIDER=voyage`, then re-running the build, fixes that and is
the single highest-value upgrade to retrieval quality.

## Tests

```
make test      # 118 tests
```

Covering canon integrity, verse-count reconciliation against known totals,
reference-parser edge cases (`3 Jn 4` is a verse, not a chapter), verse-boundary
contamination, pericope well-formedness, FTS operator injection, retrieval
behaviour, dispute detection by overlap, and the full API surface.

For the personal layer the important tests are the negative ones: that two
accounts cannot read, edit or delete each other's notes, highlights or
conversations, and that a reader's notes never reach a prompt unless their own
setting permits it — asserted by planting a marker string in a note and
checking it is absent from what the model would receive.

One regression test is worth naming. The Vulgate follows Septuagint psalm
numbering, so its "Psalm 121" is the Hebrew Psalm 122 and has a verse 9.
Normalizing spans with a `MAX` across all translations therefore stretched every
English psalm by one verse, which made a bookmark created from "Psalm 121" never
match that passage again. Spans are now clamped against the reference
translation alone.

## Production notes

- **Postgres** — SQLite is right for a prototype; the schema is plain SQL and
  moving to Postgres + pgvector is a driver swap. Do it when you need
  concurrent writes.
- **Rate limiting** — does not exist yet. Add it before exposing `/api/chat`
  publicly; it is the only endpoint that costs money per call.
- **`BIBLIA_SECRET_KEY`** — set it, or tokens are signed with a key regenerated
  at each boot and every restart signs all users out.
- **Password reset** — there is no email flow yet, so a forgotten password
  currently needs manual intervention.
- **Caching** — passage reads are deterministic and cache indefinitely.
- **Attribution** — each translation's licence is already returned by
  `/api/translations`; surface it in the UI wherever text is displayed.

## Layout

```
backend/app/
  canon.py              66-book metadata, name resolution
  db.py                 schema, vid encoding
  config.py             environment settings
  ingest/
    parsers.py          OSIS / USFX / Zefania parsers
    sources.py          translation registry
    contested.py        the interpretive-disagreement map
    run.py              corpus build
  retrieval/
    refparse.py         scripture reference parsing
    search.py           hybrid retrieval and context assembly
    embed.py            pluggable embeddings
  llm/
    prompts.py          system prompt and evidence rendering
    provider.py         pluggable chat models
  auth.py               scrypt passwords, JWT sessions, optional-auth deps
  personal.py           notes, highlights, bookmarks, history, settings
  main.py               FastAPI app
frontend/src/
  lib/narrator.js       Web Speech narration, one utterance per verse
  components/           reader, chat, narrator transport, account panels
```
