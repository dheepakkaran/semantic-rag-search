"""API tests with the language model mocked out.

`monkeypatch` replaces the generation call, so these run with no API key, no
network and no cost — which is what lets them run on every push in CI.
"""

import pytest
from fastapi.testclient import TestClient

NOTES = (
    "Cosine similarity compares the angle between two vectors and ignores "
    "their length. If the vectors are already unit length, the cosine is just "
    "their dot product."
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    import app as application
    from rag import InMemoryStore

    # A fresh store per test, so one test's documents cannot leak into another.
    application.store = InMemoryStore()
    return TestClient(application.app)


def test_health_reports_an_empty_store(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["chunks"] == 0


def test_ingest_then_search_finds_the_document(client):
    body = client.post("/ingest", json={"document_id": "embeddings", "text": NOTES}).json()
    assert body["chunks_added"] == 1

    hits = client.get("/search", params={"q": "how is nearness measured?"}).json()["hits"]
    assert hits[0]["document_id"] == "embeddings"
    assert 0.0 < hits[0]["score"] <= 1.0


def test_search_on_an_empty_store_returns_no_hits(client):
    assert client.get("/search", params={"q": "anything"}).json()["hits"] == []


def test_ask_grounds_the_answer_in_retrieved_passages(client, monkeypatch):
    client.post("/ingest", json={"document_id": "embeddings", "text": NOTES})

    seen = {}

    def fake_generate(prompt: str) -> str:
        seen["prompt"] = prompt
        return "Cosine similarity, which is a dot product for unit vectors [1]."

    monkeypatch.setattr("rag.pipeline.generate", fake_generate)

    body = client.post("/ask", json={"question": "how is nearness measured?"}).json()

    assert body["answer"].startswith("Cosine similarity")
    assert len(body["hits"]) == 1
    # The retrieved passage really was put in front of the model, numbered so
    # the model can cite it.
    assert "[1] Cosine similarity compares" in seen["prompt"]
    assert "only the notes below" in seen["prompt"]


def test_ask_with_nothing_ingested_says_so_without_calling_the_model(client, monkeypatch):
    def explode(prompt: str) -> str:
        raise AssertionError("the model must not be called when there is nothing to cite")

    monkeypatch.setattr("rag.pipeline.generate", explode)

    body = client.post("/ask", json={"question": "anything"}).json()
    assert "No documents" in body["answer"]
    assert body["hits"] == []


def test_deleting_a_document_removes_it_from_search(client):
    client.post("/ingest", json={"document_id": "embeddings", "text": NOTES})

    body = client.delete("/documents/embeddings").json()
    assert body["chunks_removed"] == 1

    assert client.get("/search", params={"q": "cosine"}).json()["hits"] == []


@pytest.mark.parametrize(
    "method,url,payload",
    [
        ("post", "/ingest", {"document_id": "x", "text": "   "}),
        ("post", "/ask", {"question": "  "}),
    ],
)
def test_blank_input_is_rejected(client, method, url, payload):
    assert getattr(client, method)(url, json=payload).status_code == 400


def test_blank_query_is_rejected(client):
    assert client.get("/search", params={"q": "  "}).status_code == 400


def test_k_outside_the_allowed_range_is_rejected(client):
    assert client.post("/ask", json={"question": "x", "k": 0}).status_code == 422
    assert client.post("/ask", json={"question": "x", "k": 50}).status_code == 422
