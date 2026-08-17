"""HTTP layer over the RAG pipeline.

    GET    /health              chunk count and the provider chain
    GET    /providers           which models can be picked, and which are ready
    POST   /ingest              store a document's chunks and vectors
    DELETE /documents/{id}      drop a document's chunks
    GET    /search              the retrieval half — which passages match?
    POST   /ask                 the full round trip, with automatic fallback

This service owns everything that needs Python: the embedding model, the
vector maths and the calls to the language models. The Node API in front of it
owns document metadata and talks to this service over HTTP.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from rag import ask, search_chunks
from rag.llm import DEFAULT_MODELS, LLMError, chain, is_available, model_for
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
    # Pinning a provider disables fallback: an explicit choice is not silently
    # overridden.
    provider: str | None = None


class AttemptResponse(BaseModel):
    provider: str
    model: str
    status: int
    message: str


class AskResponse(BaseModel):
    question: str
    answer: str
    provider: str
    model: str
    fallbacks: list[AttemptResponse]
    hits: list[HitResponse]


class ProviderResponse(BaseModel):
    name: str
    model: str
    ready: bool
    in_chain: bool


@app.get("/health")
def health() -> dict:
    """Used by Docker Compose and the Kubernetes readiness probe."""
    return {"status": "ok", "chunks": len(store), "chain": chain()}


@app.get("/providers", response_model=list[ProviderResponse])
def providers() -> list[ProviderResponse]:
    """What the UI's model picker offers.

    `ready` means a key is present, not that the provider will succeed — quota
    is only discoverable by asking.
    """
    order = chain()
    return [
        ProviderResponse(
            name=name,
            model=model_for(name),
            ready=is_available(name),
            in_chain=name in order,
        )
        for name in DEFAULT_MODELS
    ]


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
    return {
        "document_id": document_id,
        "chunks_removed": store.delete_document(document_id),
    }


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

    if request.provider and request.provider not in DEFAULT_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown provider {request.provider!r}; "
            f"expected any of {sorted(DEFAULT_MODELS)}",
        )

    try:
        result = ask(store, request.question, request.k, request.provider)
    except LLMError as exc:
        # Pass the provider's own status through. A 429 for an exhausted quota
        # is something the caller can wait out; reporting it as a 500 tells
        # them to look for a bug that is not there.
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc

    return AskResponse(
        question=request.question,
        answer=result.text,
        provider=result.provider,
        model=result.model,
        fallbacks=[
            AttemptResponse(
                provider=a.provider, model=a.model, status=a.status, message=a.message
            )
            for a in result.fallbacks
        ],
        hits=[_to_response(h) for h in result.hits],
    )


def _to_response(hit) -> HitResponse:
    return HitResponse(document_id=hit.document_id, text=hit.text, score=hit.score)
