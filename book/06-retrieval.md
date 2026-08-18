# Chapter 6 — Retrieval

**File:** `python-service/rag/retriever.py`

## Where we are

Chunks exist. Each has a vector. A question arrives and also becomes a vector.

All that remains is: **which chunk vectors are closest to the question vector?**

This chapter is the shortest piece of real code in the project and the part
worth understanding most thoroughly.

## Measuring closeness

Two vectors, and we want a number for how similar they are. The standard choice
is **cosine similarity**: the cosine of the angle between them.

```
        ↗ B
       /
      /  θ small  →  similar
     /
    •————————→ A


        ↑ B
        |
        |  θ = 90°  →  unrelated
        |
        •————————→ A
```

| Angle | Cosine | Meaning |
|---|---|---|
| 0° | 1.0 | Same direction — as similar as possible |
| 90° | 0.0 | Unrelated |
| 180° | −1.0 | Opposite |

Angle, not distance. Why? Because the *length* of an embedding does not carry
meaning we want. Two passages on the same topic point the same way whether one
is longer than the other. Cosine ignores length and looks only at direction.

## The formula, and why ours is simpler

Cosine similarity in general:

```
                A · B
cos(θ)  =  ─────────────
            |A| × |B|
```

Dot product on top, the two lengths on the bottom. The division is what removes
the effect of length.

But in Chapter 5 we normalised every vector to length 1. So `|A| = 1` and
`|B| = 1`, the denominator is `1 × 1 = 1`, and:

```
cos(θ)  =  A · B
```

**The cosine similarity is just the dot product.** No division, no square roots.

That one decision — `normalize_embeddings=True` — turns the similarity
calculation into a single multiply-and-add. It is why the whole retrieval step
fits in two lines.

## The two lines

```python
scores = vectors @ query_vector
best = np.argsort(scores)[::-1][:k]
```

That is retrieval. Everything else in the file is bookkeeping.

**Line 1.** `vectors` is a matrix with one row per chunk, 384 columns.
`query_vector` is one row of 384. The `@` operator multiplies them, producing one
score per chunk — the dot product of that chunk against the question, which we
just established *is* the cosine similarity.

```
vectors        query        scores
(5000 × 384)  @  (384,)  =  (5000,)
```

NumPy does all five thousand dot products in one call, in compiled code, using
your CPU's vector instructions. This is why it is fast.

**Line 2.** `argsort` returns the *indices* that would sort the array, smallest
first. `[::-1]` reverses it to largest first. `[:k]` takes the top k.

## The whole file

```python
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


def search(query, chunks, vectors, k=4) -> list[Hit]:
    """Return the `k` chunks closest in meaning to `query`, best first."""
    if not chunks or vectors is None or len(vectors) == 0:
        return []

    query_vector = embed([query])[0]

    # Both sides are unit vectors, so the dot product *is* the cosine
    # similarity — no division needed.
    scores = vectors @ query_vector

    k = min(k, len(chunks))
    best = np.argsort(scores)[::-1][:k]

    return [Hit(chunks[i].document_id, chunks[i].text, float(scores[i])) for i in best]
```

Three defensive details:

**The empty check.** An empty store is normal, not exceptional — it is what a
fresh deployment looks like. Return an empty list rather than crash on an
operation that has nothing to operate on.

**`k = min(k, len(chunks))`.** Ask for 4 results from a store holding 2 and you
should get 2, not an error. Slicing past the end is harmless in Python, but
being explicit documents the intent.

**`float(scores[i])`.** NumPy returns `np.float32`, which is not JSON
serialisable. Convert at the boundary, so nothing downstream has to know NumPy
was involved.

## Why there is no vector database

This is the design decision people ask about most, so here is the reasoning
before the measurement in Chapter 19.

A vector database — Pinecone, Weaviate, pgvector, FAISS — builds an index so you
do not have to compare against every vector. That matters enormously at a
million vectors. Does it matter at five thousand?

The measurement, from Chapter 19:

```
at 5,005 chunks a query splits into:
  encoding the question   3.80 ms
  ranking every chunk     0.08 ms   ← 2% of the query
```

Ranking all five thousand chunks takes 0.08 milliseconds. The other 3.80 ms is
one forward pass through the embedding model to turn the question into a vector —
which an index does not touch at all.

So a vector database would optimise 2% of the request, and add a dependency, a
container, a network hop and a failure mode.

**The argument has a limit and it is important to say so.** The linear scan grows
with the corpus; an index does not. Somewhere above 5,000 the lines cross, and at
a million vectors the scan is the bottleneck and the answer flips. The claim here
is only that 5,000 is nowhere near that point.

That last paragraph is the difference between a defensible decision and a
prejudice. "I did not need one at this size, and here is where that stops being
true" beats "vector databases are overkill" in every conversation.

## Why there is no LangChain

LangChain, LlamaIndex and similar frameworks package this pattern. Using one,
this chapter would be:

```python
from langchain.vectorstores import FAISS
retriever = FAISS.from_texts(chunks, embeddings).as_retriever(k=4)
```

Two lines instead of twenty. Genuinely less code.

It was not used here because the twenty lines are the part worth understanding.
Behind that abstraction is exactly `vectors @ query_vector` and an `argsort` —
and if you have never written them, you cannot reason about what the framework
is doing when retrieval starts returning the wrong passages.

There is also a practical cost: a framework brings its own abstractions, its own
release cadence and its own bugs, in exchange for code you could have written in
an afternoon.

> This is a good interview answer, and it is honest rather than contrarian:
>
> *"I wrote the retrieval directly because I wanted to understand it rather than
> hide it behind an abstraction. On a bigger system with many retrieval
> strategies I would reconsider — the framework earns its place when there are
> ten of these, not one."*

## Edge cases worth knowing

**Cosine can be negative.** Vectors pointing in opposite directions give a
negative score. In practice with this model it rarely goes below zero, but the
front end clamps before turning a score into a bar width:

```typescript
const fraction = Math.max(0, Math.min(1, hit.score));
```

Without the clamp, a negative score would produce a negative CSS width, which
browsers ignore silently — a bug that looks like nothing at all.

**Scores are not probabilities.** 0.57 does not mean "57% relevant". They are
only meaningful relative to each other, in the same query. Comparing scores
across different questions is meaningless.

**Absolute values run lower than people expect.** A strong match in this system
scores around 0.5–0.6, not 0.9. That is normal for this model. What matters is
the gap between the top hit and the rest.

## Seeing it work

```bash
cd python-service
./venv/bin/python cli.py sample_notes.txt search "what stops a model memorising?"
```

```
ingested 5 chunks from sample_notes.txt

[1] score 0.455
    the family of tricks that push back against overfitting. Weight decay
    adds a penalty for large weights, which keeps the model from leaning...

[2] score 0.376
    generalisation A model that has memorised its training set can score
    perfectly on that set and still be useless on anything new...
```

The question contains none of *regularisation*, *dropout*, or *weight decay*.
The passage explaining all three came first.

That is Chapter 1's problem, solved, in two lines of NumPy.

---

## What you should take from this chapter

| | |
|---|---|
| Cosine similarity | The cosine of the angle — ignores length, keeps direction |
| Why our version is simpler | Unit vectors make the denominator 1, so cosine = dot product |
| The whole search | `vectors @ query_vector` then `argsort` |
| Why no vector DB | Ranking is 2% of a query at this size — with a stated limit |
| Why no framework | The twenty lines are the part worth understanding |

---

**Next:** [Chapter 7 — Testing retrieval](07-testing-retrieval.md), where we test
something that has no single right answer.
