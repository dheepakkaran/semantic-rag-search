"""Where chunks and their vectors live.

Two implementations behind the same three methods (`add`, `load`, `len`):

    InMemoryStore   nothing to install; used by tests and by `cli.py`
    MongoStore      survives a restart; used when MONGO_URI is set

Chunks are a natural fit for MongoDB rather than a relational table: each one
is a blob of text plus a variable-length vector, with no relationships to
model. Document *metadata* is relational and lives in PostgreSQL, owned by the
Node API.

Known limit: `MongoStore.load()` reads every vector on every query. That is
fine into the low thousands of chunks — the read and the dot product together
stay in the low tens of milliseconds. Past that this needs either an
in-process cache or a real vector index; neither is worth adding for a
personal notes collection.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .chunker import chunk_text
from .embedder import embed


@dataclass
class Chunk:
    """One window of a document."""

    document_id: str
    text: str


class Store(Protocol):
    """What the pipeline needs from a store."""

    def add(self, document_id: str, text: str) -> int:
        """Chunk and embed `text`, save it, return how many chunks were added."""

    def load(self) -> tuple[list[Chunk], np.ndarray | None]:
        """Return every chunk and a matching array of vectors."""

    def delete_document(self, document_id: str) -> int:
        """Remove a document's chunks, return how many were removed."""

    def __len__(self) -> int:
        ...


class InMemoryStore:
    """Keeps everything in a list and one NumPy array."""

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._vectors: np.ndarray | None = None

    def add(self, document_id: str, text: str, size: int = 120, overlap: int = 20) -> int:
        texts = chunk_text(text, size, overlap)
        if not texts:
            return 0

        vectors = embed(texts)
        self._chunks.extend(Chunk(document_id, t) for t in texts)
        self._vectors = (
            vectors if self._vectors is None else np.vstack([self._vectors, vectors])
        )
        return len(texts)

    def load(self) -> tuple[list[Chunk], np.ndarray | None]:
        return self._chunks, self._vectors

    def delete_document(self, document_id: str) -> int:
        keep = [i for i, c in enumerate(self._chunks) if c.document_id != document_id]
        removed = len(self._chunks) - len(keep)
        if removed == 0:
            return 0

        self._chunks = [self._chunks[i] for i in keep]
        self._vectors = self._vectors[keep] if keep else None
        return removed

    def __len__(self) -> int:
        return len(self._chunks)


class MongoStore:
    """Keeps chunks as documents, each with its vector stored as an array."""

    def __init__(self, uri: str, database: str = "rag", collection: str = "chunks") -> None:
        from pymongo import MongoClient

        self._collection = MongoClient(uri)[database][collection]
        # Lets the Node API delete a document's chunks without a full scan.
        self._collection.create_index("document_id")

    def add(self, document_id: str, text: str, size: int = 120, overlap: int = 20) -> int:
        texts = chunk_text(text, size, overlap)
        if not texts:
            return 0

        vectors = embed(texts)
        self._collection.insert_many(
            [
                {
                    "document_id": document_id,
                    "position": position,
                    "text": chunk,
                    "vector": vector.tolist(),
                }
                for position, (chunk, vector) in enumerate(zip(texts, vectors))
            ]
        )
        return len(texts)

    def load(self) -> tuple[list[Chunk], np.ndarray | None]:
        documents = list(
            self._collection.find({}, {"_id": 0, "document_id": 1, "text": 1, "vector": 1})
        )
        if not documents:
            return [], None

        chunks = [Chunk(d["document_id"], d["text"]) for d in documents]
        vectors = np.array([d["vector"] for d in documents], dtype=np.float32)
        return chunks, vectors

    def delete_document(self, document_id: str) -> int:
        result = self._collection.delete_many({"document_id": document_id})
        return result.deleted_count

    def __len__(self) -> int:
        return self._collection.count_documents({})


def build_store() -> Store:
    """MongoStore when MONGO_URI is set, otherwise an in-memory store.

    Falling back to memory means the service still starts with no database,
    which keeps tests and a bare `uvicorn app:app` working.
    """
    uri = os.getenv("MONGO_URI")
    if uri:
        return MongoStore(uri)
    return InMemoryStore()
