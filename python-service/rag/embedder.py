"""Turn text into vectors with a small model that runs locally on the CPU.

Embedding happens locally rather than through an API because it is a bulk
operation: a single document can be hundreds of chunks, and every chunk needs
a vector. MiniLM is 22 MB and embeds a few hundred chunks in about a second,
so there is nothing to gain from spending API quota on it.

Vectors are normalized to unit length. That makes cosine similarity a plain
dot product, which is why `retriever.py` can rank with a single matrix
multiply.
"""

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Load the model on first use and reuse it afterwards.

    Loading takes a few seconds, so it is deliberately not done at import
    time — tests that never embed anything should not pay for it.
    """
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed(texts: list[str]) -> np.ndarray:
    """Embed `texts` into a (len(texts), dim) array of unit vectors."""
    return get_model().encode(texts, normalize_embeddings=True)
