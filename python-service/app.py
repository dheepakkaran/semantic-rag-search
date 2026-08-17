"""HTTP layer over the RAG pipeline.

Three endpoints, matching the three things the pipeline does:

    POST /ingest   store a document's chunks and vectors
    GET  /search   the retrieval half — which passages match?
    POST /ask      the full round trip — an answer grounded in those passages

This service owns everything that needs Python: the embedding model, the
vector maths and the call to the language model. The Node API in front of it
owns document metadata and talks to this service over HTTP.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from rag import ask, search_chunks
from rag.store import build_store

load_dotenv()

app = FastAPI(title="Semantic RAG Search — retrieval service")
store = build_store()


class IngestRequest(BaseModel):
    document_id: str
    text: str


class IngestResponse(BaseModel):
    document_id: str
    chunks_added: int


class HitResponse(BaseModel):
    document_id: str
    text: str
    score: float


class SearchResponse(BaseModel):
    query: str
    hits: list[HitResponse]


class AskRequest(BaseModel):
    question: str
    k: int = Field(default=4, ge=1, le=10)


class AskResponse(BaseModel):
    question: str
    answer: str
    hits: list[HitResponse]


@app.get("/health")
def health() -> dict:
    """Used by Docker Compose and the Kubernetes readiness probe."""
    return {"status": "ok", "chunks": len(store), "provider": os.getenv("LLM_PROVIDER", "gemini")}


@app.post("/ingest", response_model=IngestResponse)
def ingest(request: IngestRequest) -> IngestResponse:
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="text is empty")

    added = store.add(request.document_id, request.text)
    return IngestResponse(document_id=request.document_id, chunks_added=added)


@app.delete("/documents/{document_id}")
def delete_document(document_id: str) -> dict:
    """Drop a document's chunks. The Node API calls this when a document is
    deleted so the vector store does not keep answering from it."""
    return {"document_id": document_id, "chunks_removed": store.delete_document(document_id)}


@app.get("/search", response_model=SearchResponse)
def search(q: str, k: int = 4) -> SearchResponse:
    if not q.strip():
        raise HTTPException(status_code=400, detail="q is empty")

    hits = search_chunks(store, q, k)
    return SearchResponse(query=q, hits=[_to_response(h) for h in hits])


@app.post("/ask", response_model=AskResponse)
def ask_question(request: AskRequest) -> AskResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question is empty")

    try:
        answer, hits = ask(store, request.question, request.k)
    except RuntimeError as exc:
        # Raised when the chosen provider has no API key configured.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return AskResponse(
        question=request.question,
        answer=answer,
        hits=[_to_response(h) for h in hits],
    )


def _to_response(hit) -> HitResponse:
    return HitResponse(document_id=hit.document_id, text=hit.text, score=hit.score)
