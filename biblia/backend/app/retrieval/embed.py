"""Dense retrieval over pericopes.

Design note: embeddings are built once per *passage*, in a single reference
translation — never once per translation. Eleven English renderings of Romans
8:28 are near-identical points in embedding space; indexing all of them makes a
query for "God works things for good" return the same passage eleven times and
push genuinely different passages off the result list. Retrieval finds the
passage; the translation fan-out happens afterward, at read time.

Providers are pluggable. The default runs entirely offline (TF-IDF reduced by
SVD, i.e. latent semantic analysis) so the system is functional with no API key
and no model download. Set BIBLIA_EMBED_PROVIDER=voyage or =openai plus the
matching key to swap in real neural embeddings without touching anything else;
the vectors table and query path are identical.
"""

from __future__ import annotations

import io
import os
import pickle
import sqlite3
from typing import Protocol

import numpy as np

from .. import config


class EmbeddingProvider(Protocol):
    name: str
    dim: int

    def fit(self, docs: list[str]) -> None: ...
    def embed_documents(self, docs: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...
    def state(self) -> bytes: ...
    def load_state(self, blob: bytes) -> None: ...


def _l2(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    if m.ndim == 1:
        n = np.linalg.norm(m) or 1.0
        return (m / n).astype(np.float32)
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (m / n).astype(np.float32)


# ---------------------------------------------------------------------------
# offline default: latent semantic analysis
# ---------------------------------------------------------------------------


class LSAProvider:
    """TF-IDF + truncated SVD, fitted on the corpus itself.

    Not competitive with a modern neural embedder, but it needs no network, no
    key and no model weights, and on a corpus this homogeneous it retrieves
    thematically related passages well enough to exercise the whole pipeline.
    """

    name = "lsa"

    def __init__(self, dim: int = 320):
        self.dim = dim
        self._vec = None
        self._svd = None

    def fit(self, docs: list[str]) -> None:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vec = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            max_features=60_000,
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=2,
        )
        X = self._vec.fit_transform(docs)
        self.dim = min(self.dim, max(2, min(X.shape) - 1))
        self._svd = TruncatedSVD(n_components=self.dim, random_state=0)
        self._svd.fit(X)

    def embed_documents(self, docs: list[str]) -> np.ndarray:
        return _l2(self._svd.transform(self._vec.transform(docs)))

    def embed_query(self, text: str) -> np.ndarray:
        return _l2(self._svd.transform(self._vec.transform([text]))[0])

    def state(self) -> bytes:
        buf = io.BytesIO()
        pickle.dump({"vec": self._vec, "svd": self._svd, "dim": self.dim}, buf)
        return buf.getvalue()

    def load_state(self, blob: bytes) -> None:
        d = pickle.loads(blob)
        self._vec, self._svd, self.dim = d["vec"], d["svd"], d["dim"]


# ---------------------------------------------------------------------------
# API providers
# ---------------------------------------------------------------------------


class _HTTPProvider:
    """Shared batching logic for hosted embedding APIs."""

    name = "http"
    dim = 1024
    batch = 96

    def _call(self, texts: list[str], kind: str) -> np.ndarray:
        raise NotImplementedError

    def fit(self, docs: list[str]) -> None:
        return None

    def embed_documents(self, docs: list[str]) -> np.ndarray:
        out = []
        for i in range(0, len(docs), self.batch):
            out.append(self._call(docs[i:i + self.batch], "document"))
        return _l2(np.vstack(out))

    def embed_query(self, text: str) -> np.ndarray:
        return _l2(self._call([text], "query")[0])

    def state(self) -> bytes:
        return b""

    def load_state(self, blob: bytes) -> None:
        return None


class VoyageProvider(_HTTPProvider):
    name = "voyage"
    dim = 1024

    def __init__(self, model: str = "voyage-3"):
        self.model = model
        self.key = config.settings.voyage_api_key

    def _call(self, texts: list[str], kind: str) -> np.ndarray:
        import httpx

        r = httpx.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.key}"},
            json={"input": texts, "model": self.model, "input_type": kind},
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()["data"]
        return np.array([d["embedding"] for d in data], dtype=np.float32)


class OpenAIProvider(_HTTPProvider):
    name = "openai"
    dim = 1536

    def __init__(self, model: str = "text-embedding-3-small"):
        self.model = model
        self.key = config.settings.openai_api_key

    def _call(self, texts: list[str], kind: str) -> np.ndarray:
        import httpx

        r = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.key}"},
            json={"input": texts, "model": self.model},
            timeout=120,
        )
        r.raise_for_status()
        data = sorted(r.json()["data"], key=lambda d: d["index"])
        return np.array([d["embedding"] for d in data], dtype=np.float32)


def get_provider() -> EmbeddingProvider:
    kind = (config.settings.embed_provider or "lsa").lower()
    if kind == "voyage" and config.settings.voyage_api_key:
        return VoyageProvider()
    if kind == "openai" and config.settings.openai_api_key:
        return OpenAIProvider()
    return LSAProvider()


# ---------------------------------------------------------------------------
# index build + query
# ---------------------------------------------------------------------------


def _pericope_docs(conn: sqlite3.Connection) -> tuple[list[int], list[str]]:
    from ..ingest.sources import REFERENCE

    rows = conn.execute(
        """SELECT p.id, p.ref, p.title,
                  (SELECT group_concat(v.text, ' ')
                     FROM verses v JOIN translations t ON t.id = v.translation_id
                    WHERE t.abbrev = ? AND v.vid BETWEEN p.start_vid AND p.end_vid) AS body
             FROM pericopes p ORDER BY p.start_vid""",
        (REFERENCE,),
    ).fetchall()
    ids, docs = [], []
    for r in rows:
        body = r["body"] or ""
        if not body.strip():
            continue
        ids.append(r["id"])
        # title carries real signal ("The Creation", "Love is patient")
        docs.append(f"{r['title']}. {r['ref']}. {body}")
    return ids, docs


def build_index(conn: sqlite3.Connection) -> int:
    ids, docs = _pericope_docs(conn)
    if not ids:
        print("  no pericope bodies; skipping embeddings", flush=True)
        return 0

    provider = get_provider()
    provider.fit(docs)
    vecs = provider.embed_documents(docs)

    cur = conn.cursor()
    cur.execute("DELETE FROM pericope_vectors")
    cur.executemany(
        "INSERT INTO pericope_vectors (pericope_id, dim, vec) VALUES (?,?,?)",
        [(pid, int(vecs.shape[1]), vecs[i].astype(np.float32).tobytes())
         for i, pid in enumerate(ids)],
    )
    cur.execute("DELETE FROM embedding_meta")
    cur.execute(
        "INSERT INTO embedding_meta (id, provider, model, dim, payload) VALUES (1,?,?,?,?)",
        (provider.name, getattr(provider, "model", provider.name),
         int(vecs.shape[1]), provider.state()),
    )
    conn.commit()
    print(f"  {len(ids)} pericope vectors  dim={vecs.shape[1]}  provider={provider.name}",
          flush=True)
    return len(ids)


class VectorIndex:
    """In-memory cosine index. The whole matrix is ~1,500 x 320 floats, so a
    brute-force dot product is faster than any ANN structure would be here."""

    def __init__(self, conn: sqlite3.Connection):
        self.ok = False
        meta = conn.execute("SELECT * FROM embedding_meta WHERE id = 1").fetchone()
        if not meta:
            return
        rows = conn.execute(
            "SELECT pericope_id, vec FROM pericope_vectors ORDER BY pericope_id"
        ).fetchall()
        if not rows:
            return
        self.ids = np.array([r["pericope_id"] for r in rows], dtype=np.int64)
        self.mat = np.vstack(
            [np.frombuffer(r["vec"], dtype=np.float32) for r in rows]
        )
        self.provider = get_provider()
        if meta["payload"]:
            try:
                self.provider.load_state(meta["payload"])
            except Exception:
                return
        self.ok = True

    def search(self, query: str, k: int = 12) -> list[tuple[int, float]]:
        if not self.ok:
            return []
        try:
            q = self.provider.embed_query(query)
        except Exception:
            return []
        if q.shape[0] != self.mat.shape[1]:
            return []
        scores = self.mat @ q
        k = min(k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(int(self.ids[i]), float(scores[i])) for i in top]
