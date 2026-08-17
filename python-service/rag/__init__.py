"""Semantic RAG Search — retrieval and grounded question answering."""

from .llm import Attempt, Generation, LLMError, chain, generate, is_available, model_for
from .pipeline import Answer, ask, search_chunks
from .retriever import Hit
from .store import Chunk, InMemoryStore, MongoStore, Store, build_store

__all__ = [
    "Answer",
    "Attempt",
    "Chunk",
    "Generation",
    "Hit",
    "InMemoryStore",
    "LLMError",
    "MongoStore",
    "Store",
    "ask",
    "build_store",
    "chain",
    "generate",
    "is_available",
    "model_for",
    "search_chunks",
]
