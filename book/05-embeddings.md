# Chapter 5 — Embeddings

**File:** `python-service/rag/embedder.py`

## The one idea

An **embedding** is a list of numbers that stands in for a piece of text, chosen
so that texts with similar meanings get similar lists.

That is the entire concept. Everything else is detail.

```python
"cat"      →  [-0.041,  0.118, -0.007, ...]   384 numbers
"kitten"   →  [-0.038,  0.121, -0.011, ...]   384 numbers, very close
"gradient" →  [ 0.203, -0.088,  0.156, ...]   384 numbers, far away
```

Nobody chose those numbers by hand. A model produced them, and it learned to
produce them by reading an enormous amount of text.

## Why a list of numbers is useful

Because you can do arithmetic on it.

You cannot subtract "cat" from "kitten". You *can* subtract one list of numbers
from another and get a distance. Once meaning is numbers, "how similar are these
two texts?" becomes a calculation instead of a judgement.

That is the trade the whole field is built on: give up on understanding language
directly, and instead find a numeric representation where distance behaves like
similarity.

## How many numbers?

The model in this project produces **384** per piece of text. Other models use
768, 1024, 1536.

More dimensions means more room to record distinctions, and more storage and
compute per comparison. 384 is on the small end, which is deliberate — the model
is 22 MB and runs on a laptop CPU in milliseconds.

You do not choose the number. The model does. You choose the model.

## Choosing the model

This project uses `all-MiniLM-L6-v2`.

| | |
|---|---|
| Size on disk | **22 MB** |
| Output dimensions | 384 |
| Speed | ~660 chunks/second on a laptop CPU |
| Cost | free, runs locally |

There are better models. There are models with 1024 dimensions that score higher
on retrieval benchmarks. MiniLM was chosen because it is small enough to run on
the same box as everything else, fast enough that retrieval feels instant, and
good enough that it finds the right passage.

"Good enough and small" beats "better and heavy" when the better one would mean
a GPU, an API bill, or a slower demo.

## The code

```python
import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Load the model on first use and reuse it afterwards."""
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed(texts: list[str]) -> np.ndarray:
    """Embed `texts` into a (len(texts), dim) array of unit vectors."""
    return get_model().encode(texts, normalize_embeddings=True)
```

Twelve lines, and two of the decisions in them are worth explaining.

## Decision 1: load the model lazily

The model is not loaded when the module is imported. It is loaded the first time
someone actually embeds something.

Loading takes a few seconds. If it happened at import time, every test that
touches this module would pay for it — including the tests that never embed
anything, like the chunker tests. Lazy loading keeps the fast tests fast.

The `global` statement makes some people uncomfortable. Here it is doing exactly
what it should: caching an expensive object so it is created once per process.

## Decision 2: normalise the vectors

`normalize_embeddings=True` scales every vector to length 1.

This looks like a detail and is actually the most consequential line in the file.
The next chapter shows why: with unit vectors, cosine similarity becomes a plain
dot product, and the entire retrieval step collapses into one matrix multiply.

Here is what "length 1" means. A vector has a direction and a length. Normalising
throws away the length and keeps only the direction:

```
before:  [3, 4]           length 5
after:   [0.6, 0.8]       length 1, same direction
```

For similarity we only care about direction. Two texts about the same topic point
the same way; how "long" their vectors are carries no meaning we want.

Verify it:

```python
import numpy as np
from rag.embedder import embed

vectors = embed(["dropout switches off units", "the learning rate is the step size"])
print(vectors.shape)
print(np.linalg.norm(vectors, axis=1))
```

```
(2, 384)
[1. 1.]
```

Two vectors, 384 numbers each, both exactly length 1.

## Why embed locally instead of calling an API

Every hosted model provider sells embeddings. Using one would remove a
900 MB dependency. This project does not, and the reason is worth being explicit
about because it comes up in interviews.

**Embedding is a bulk, one-time operation.** A single document becomes hundreds
of chunks, and every chunk needs a vector. Through an API that is hundreds of
calls, paid for, rate-limited, and slow. Locally it is one function call that
finishes in under a second.

**Changing the model means re-embedding everything.** Vectors from one model are
meaningless to another — you cannot compare a MiniLM vector to an OpenAI vector.
So the day you switch, you re-embed your entire corpus. Doing that locally is
free; doing it through an API is a bill.

**Generation is where quality actually matters.** The retrieved passage is the
same text either way. What differs between a cheap and an expensive model is how
well the *answer* reads — and that is generation, not embedding.

So the split this project uses:

```
embedding    →  local, free, unlimited
generation   →  hosted API, better quality
```

That sentence is a good answer to *"how did you decide what runs where?"*

## What the model actually does

You do not need this to use it, but it helps to know it is not magic.

The model is a small transformer. Text goes in as tokens; each layer builds a
representation that takes surrounding words into account; the per-token outputs
are averaged into one vector for the whole input.

The useful part is the training. The model was shown enormous numbers of text
pairs and trained so that related pairs end up close together and unrelated pairs
end up far apart. Nobody wrote a rule saying *dropout* relates to *memorising* —
it emerged from seeing them used in the same contexts, over and over.

That is why the vocabulary mismatch from Chapter 1 stops being a problem. The
model never sees your words as characters. It sees them as positions that were
shaped by usage.

## A worked example, and an uncomfortable result

```python
from rag.embedder import embed

texts = [
    "Dropout randomly switches off units during training.",
    "Weight decay adds a penalty for large weights.",
    "Heat the pan until a drop of water skitters across it.",
]
vectors = embed(texts)
question = embed(["how do I stop my network memorising?"])[0]

for text, vector in zip(texts, vectors):
    print(f"{vector @ question:.3f}  {text[:48]}")
```

Run it and you get this:

```
0.238  Dropout randomly switches off units during train
0.101  Weight decay adds a penalty for large weights.
0.133  Heat the pan until a drop of water skitters acro
```

The right sentence won — 0.238 for dropout, against a question sharing none of
its words. Good.

But look at the other two. **The cooking sentence scored higher than weight
decay.** 0.133 against 0.101.

That is not what a tidy tutorial would print. It is what actually happens, and
it is worth more than the tidy version.

## Why the cooking sentence beat weight decay

These are single short sentences, not chunks. About ten words each.

An embedding of ten words is a weak signal. There is very little text for the
model to work with, so the vector lands in a fairly generic region and small
accidents — shared function words, sentence rhythm, common phrasing — start to
matter as much as topic. The gap between "somewhat related" and "unrelated"
collapses.

Give the model more text and the signal strengthens. Here is the same kind of
question against real 120-word chunks from the actual notes, from Chapter 6:

```
[1] score 0.455   ...weight decay adds a penalty for large weights...
[2] score 0.376   ...a model that has memorised its training set...
```

Higher scores, and a clean ordering with no surprises.

## This is Chapter 4's lesson again

Recall the chunk-size measurement:

| size | top score | right passage? |
|---|---|---|
| 120 | 0.404 | yes |
| 60 | 0.408 | **no** |

Same phenomenon. At 60 words the chunks were too short to be reliably *about*
anything, so the scores became noisy — high, but pointing at the wrong text.

The ten-word sentences above are an extreme version of that, and they show the
mechanism clearly:

> **Short text produces noisy embeddings.** Not wrong, not useless — noisy. The
> top match is often still right, but the ranking below it stops being
> trustworthy.

This is exactly why the system chunks at 120 words rather than by sentence, and
why you should be suspicious of any retrieval demo built on one-line examples.
One-liners are the least reliable input this technology has.

## What the example does still prove

Do not lose the actual result in the caveat. The question was:

> how do I stop my network memorising?

It contains no *dropout*, no *regularisation*, no *overfitting*. The sentence
about dropout still came first. A keyword search would have returned nothing at
all.

The mechanism works. It just works better with more text — which is what the rest
of the system gives it.

## Practical notes

**First run downloads the model.** About 90 MB, cached in `~/.cache/huggingface`
afterwards. In Chapter 20 we bake it into the Docker image so a container never
downloads on its first request.

**Embed in batches.** `embed(["a", "b", "c"])` is much faster than three separate
calls — the model processes them together.

**The numbers mean nothing individually.** Dimension 47 is not "how much this
text is about animals". The dimensions are not interpretable. Only distances
between whole vectors carry meaning.

---

## What you should take from this chapter

| | |
|---|---|
| An embedding is | A list of numbers standing in for text, where near = similar |
| Dimensions | 384 here; the model decides, you pick the model |
| Why MiniLM | 22 MB, CPU, ~660 chunks/s, good enough |
| Why normalise | Makes cosine similarity a plain dot product (Chapter 6) |
| Why local | Bulk one-time job; re-embedding is free; quality belongs to generation |

---

**Next:** [Chapter 6 — Retrieval](06-retrieval.md), where two lines of NumPy do
all the searching.
