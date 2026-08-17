"""Rank chunks against a query by cosine similarity.

This is the "R" in RAG. There is no vector database here on purpose: with a
few thousand chunks a single NumPy matrix multiply is already instant, and
keeping it explicit makes the ranking step readable.
"""

from dataclasses import dataclass

import numpy as np

from .embedder import embed
from .store import Chunk


@dataclass
class Hit:
    """One retrieved chunk and how close it was to the query."""

    document_id: str
    text: str
    score: float


def search(
    query: str,
    chunks: list[Chunk],
    vectors: np.ndarray | None,
    k: int = 4,
) -> list[Hit]:
    """Return the `k` chunks closest in meaning to `query`, best first."""
    if not chunks or vectors is None or len(vectors) == 0:
        return []

    query_vector = embed([query])[0]

    # Both sides are unit vectors, so the dot product *is* the cosine
    # similarity — no division needed.
    scores = vectors @ query_vector

    k = min(k, len(chunks))
    best = np.argsort(scores)[::-1][:k]

    return [
        Hit(chunks[i].document_id, chunks[i].text, float(scores[i])) for i in best
    ]
