"""API integration tests, exercised through FastAPI's TestClient."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.db import DB_PATH
from app.main import app

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="corpus not built")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    d = client.get("/api/health").json()
    assert d["ok"]
    assert d["corpus"]["verses"] > 200_000
    assert d["corpus"]["translations"] >= 10


def test_translations_carry_licence_and_philosophy(client):
    ts = client.get("/api/translations").json()["translations"]
    assert len(ts) >= 10
    for t in ts:
        assert t["license"], t["abbrev"]
        assert t["philosophy"], t["abbrev"]
        # the entire corpus must be freely licensed
        assert "public domain" in t["license"].lower() or "cc" in t["license"].lower()


def test_books_endpoint(client):
    d = client.get("/api/books").json()
    assert len(d["books"]) == 66


def test_passage_with_comparison(client):
    r = client.get("/api/passage",
                   params={"ref": "Romans 8:28-30", "translation": "BSB", "compare": "KJV,YLT"})
    assert r.status_code == 200
    d = r.json()
    assert d["ref"] == "Romans 8:28-30"
    assert len(d["verses"]) == 3
    assert set(d["comparisons"]) == {"KJV", "YLT"}
    assert d["contested"], "Romans 8:28-30 should be flagged as contested"


def test_passage_translations_actually_differ(client):
    """Romans 8:28 differs by subject between the KJV and modern critical texts;
    if both render identically, the comparison feature is not working."""
    d = client.get("/api/passage",
                   params={"ref": "Romans 8:28", "translation": "BSB", "compare": "KJV"}).json()
    bsb = d["verses"][0]["text"]
    kjv = d["comparisons"]["KJV"][0]["text"]
    assert bsb != kjv


def test_chapter_endpoint(client):
    d = client.get("/api/chapter/Ps/23").json()
    assert d["ref"] == "Psalms 23"
    assert len(d["verses"]) == 6


def test_unparseable_reference_is_a_400(client):
    assert client.get("/api/passage", params={"ref": "fear not"}).status_code == 400


def test_missing_text_is_a_404(client):
    """YLT in this corpus is New Testament only."""
    r = client.get("/api/passage", params={"ref": "Genesis 1:1", "translation": "YLT"})
    assert r.status_code == 404


def test_search_returns_previews(client):
    d = client.get("/api/search", params={"q": "fear not", "k": 5}).json()
    assert d["results"]
    for r in d["results"]:
        assert r["ref"] and r["preview"]


def test_contested_all(client):
    d = client.get("/api/contested/all").json()["contested"]
    assert len(d) >= 25
    for c in d:
        assert len(c["positions"]) >= 2


def _sse(raw: str) -> list[tuple[str, dict]]:
    out = []
    for frame in raw.split("\n\n"):
        event, data = "message", []
        for line in frame.split("\n"):
            if line.startswith("event: "):
                event = line[7:].strip()
            elif line.startswith("data: "):
                data.append(line[6:])
        if data:
            try:
                out.append((event, json.loads("\n".join(data))))
            except ValueError:
                pass
    return out


def test_chat_streams_meta_and_completes(client):
    r = client.post("/api/chat", json={
        "message": "Does Romans 9 teach that God chooses individuals?",
        "translation": "BSB",
    })
    assert r.status_code == 200
    frames = _sse(r.text)
    events = [e for e, _ in frames]
    assert "meta" in events and "done" in events

    meta = next(d for e, d in frames if e == "meta")
    assert meta["session_id"]
    assert "Romans 9" in " ".join(meta["passages"])
    assert meta["contested"], "the dispute should be attached to the turn"


def test_chat_session_persists_and_anchors(client):
    first = client.post("/api/chat", json={"message": "Romans 8:28", "translation": "BSB"})
    sid = next(d for e, d in _sse(first.text) if e == "meta")["session_id"]

    # a follow-up with no reference of its own must stay on the passage
    second = client.post("/api/chat", json={
        "message": "what does that mean in context?",
        "session_id": sid, "translation": "BSB",
    })
    meta = next(d for e, d in _sse(second.text) if e == "meta")
    assert meta["session_id"] == sid
    assert any("Romans 8" in p for p in meta["passages"])

    hist = client.get(f"/api/session/{sid}").json()
    assert len(hist["messages"]) >= 4
    assert hist["anchor"].startswith("Romans 8")


def test_chat_rejects_empty_message(client):
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
