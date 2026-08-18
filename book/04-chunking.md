# Chapter 4 — Chunking

**File:** `python-service/rag/chunker.py`

## Why not embed the whole document?

The obvious thing to try is embedding each document as one vector. It fails for
two reasons.

**A single vector cannot represent many topics.** A twenty-page set of lecture
notes covers gradient descent, overfitting and embeddings. Squeeze that into one
point in space and it lands somewhere in the middle, close to nothing in
particular. Ask about dropout and it scores about the same as asking about
learning rates.

**You need to hand something small to the model.** Retrieval feeds generation.
If your unit of retrieval is a twenty-page document, you have to put twenty
pages in the prompt — which is expensive, and buries the relevant sentence in
noise.

So documents get split. The pieces are called **chunks**.

## The simplest thing that works

Split on words, in fixed-size windows:

```python
def chunk_text(text: str, size: int = 120) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]
```

Ten lines and it mostly works. But it has a real flaw.

## The boundary problem

Consider a chunk boundary landing here:

```
chunk 1: ...the symptom is easy to spot — training loss keeps falling
chunk 2: while validation loss starts climbing. The reason we hold out...
```

The sentence that answers *"how do I spot overfitting?"* has been cut in half.
Neither chunk contains the whole idea, so neither scores well, and the right
answer is invisible to the search.

This is not rare. With fixed windows, **every** sentence has a chance of landing
on a boundary, and the ones that do become unfindable.

## The fix: overlap

Let consecutive chunks share some words:

```
chunk 1:  words   0 – 119
chunk 2:  words 100 – 219      ← 20 words shared with chunk 1
chunk 3:  words 200 – 319      ← 20 words shared with chunk 2
```

A sentence cut by one boundary now sits whole inside the neighbouring chunk. The
cost is storing some text twice — with 120-word chunks and 20 words of overlap,
about 17% more.

That is a good trade. Storage is cheap; an unfindable answer is not.

## The implementation

```python
def chunk_text(text: str, size: int = 120, overlap: int = 20) -> list[str]:
    words = text.split()
    if not words:
        return []

    step = size - overlap
    if step <= 0:
        raise ValueError("overlap must be smaller than size")

    chunks = []
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start:start + size]))
        if start + size >= len(words):
            # This window already reached the end of the document; another
            # window would only repeat words we have covered.
            break
    return chunks
```

Three things are worth pointing at.

**`step = size - overlap`.** The window advances by less than its width. That
single line is the whole overlap mechanism.

**The `ValueError`.** If overlap is greater than or equal to size, `step` is
zero or negative and `range` either loops forever or produces nothing. Rather
than fail mysteriously, fail immediately with a message that says what is wrong.

**The `break`.** Without it, a 260-word document with `size=300` produces two
chunks: one containing everything, and a second containing the last ten words —
which are already inside the first. That second chunk is pure noise in the
search results. The break stops as soon as a window has reached the end.

## Choosing the size

Now the interesting part. What should `size` be?

Every RAG tutorial has a number here, usually 500 or 1000, usually with no
justification. Let us actually measure it.

The trade-off runs in both directions:

| Chunk size | What goes wrong |
|---|---|
| **Too large** | One chunk covers several topics. Its vector lands between them, close to none |
| **Too small** | A chunk has too little context to be about anything. It matches on stray words |

So there is a middle. Where?

## The experiment

Same document, same question, three sizes. The question is *"how does a model
learn?"*, and the document is a set of lecture notes covering training,
overfitting and embeddings.

```python
from rag import InMemoryStore, search_chunks

text = open("sample_notes.txt").read()

for size, overlap in [(300, 50), (120, 20), (60, 10)]:
    store = InMemoryStore()
    n = store.add("bench", text, size=size, overlap=overlap)
    hits = search_chunks(store, "how does a model learn?", k=1)
    print(f"size={size:>3}  chunks={n:>2}  score={hits[0].score:.3f}")
    print(f"   {hits[0].text[:90]}...")
```

The result:

| size | chunks | top score | right passage? |
|---|---|---|---|
| 300 | 2 | 0.363 | yes, but the chunk spans two unrelated topics |
| **120** | **5** | **0.404** | **yes** |
| 60 | 10 | **0.408** | **no** — returned the overfitting section |

## The surprise

Look at the last row again.

At 60 words the **score went up** and the answer got **worse**. The highest
similarity in the table belongs to the setting that returned the wrong passage.

That is worth sitting with, because it breaks an assumption most people carry:
that a higher similarity score means a better result.

What happened: a 60-word chunk is roughly three sentences. Three sentences from
the middle of a paragraph are often not *about* anything in particular — they
are fragments. A fragment can score highly against a question by accident,
because there is so little else in it to dilute the match.

The 120-word chunk that contains the actual explanation has more text, more of
which is unrelated to the exact question, and so scores slightly lower — while
being the passage you actually wanted.

> **The lesson: a higher score is not the goal. Retrieving the right passage is
> the goal.**
>
> If you tune a retrieval system by watching the similarity number go up, you
> can make it worse while feeling like you are making it better.

## The decision

120 words, 20 overlap. Not because a blog post said so — because at 300 the
chunks mixed topics and at 60 they stopped being about anything.

That reasoning goes in the code, where the next person will find it:

```python
"""Split a document into overlapping windows of words.

Why overlap: a sentence that answers a question can sit right on a chunk
boundary. Overlapping the windows means such a sentence stays whole in at
least one chunk.

Why 120 words: measured on the sample notes. At 300 words a chunk covers two
unrelated topics and the best match scored 0.363; at 120 it scored 0.404 and
returned the right passage. Going down to 60 scored marginally higher (0.408)
but returned the *wrong* passage — the chunk no longer held enough context to
be about anything in particular. A higher score is not the goal; retrieving
the right passage is.
"""
```

A comment that says *"chunk size is 120"* is worthless — the code says that.
A comment that says *why*, with the numbers, is the difference between code
someone can change safely and code they are afraid to touch.

## Honest limits

Two weaknesses in this chunker, both real:

**It splits on whitespace, ignoring sentences and paragraphs.** A chunk can
start mid-sentence, which reads badly when shown to a user. Splitting on
sentence boundaries would be nicer. It was not done because the retrieval works
well enough without it, and every added rule is another thing to get wrong.

**The size was tuned on one document with a handful of questions.** A proper
job would use a labelled set of question/passage pairs and measure precision
across all of them. There is no such set here, so 120 is "better than the
alternatives I tried", not "optimal".

Both of these are in the project's README under *Honest limits*, and saying them
out loud is worth more than pretending they are not there.

## Try it yourself

```bash
cd python-service
./venv/bin/python -c "
from rag.chunker import chunk_text
text = ' '.join(str(n) for n in range(300))
chunks = chunk_text(text, size=100, overlap=20)
print('chunks:', len(chunks))
print('chunk 2 starts at word:', chunks[1].split()[0])
print('overlap check:', chunks[0].split()[-20:] == chunks[1].split()[:20])
"
```

```
chunks: 4
chunk 2 starts at word: 80
overlap check: True
```

The window advanced by 80 (`100 - 20`), and the last twenty words of chunk 1 are
the first twenty of chunk 2. Exactly as intended.

---

## What you should take from this chapter

| | |
|---|---|
| Why chunk | One vector cannot hold many topics; prompts have limits |
| Why overlap | Sentences land on boundaries and become unfindable |
| The trade-off | Too big mixes topics; too small loses context |
| The measurement | 300 → 0.363, 120 → 0.404, 60 → 0.408 but **wrong passage** |
| The lesson | Higher score ≠ better retrieval |

---

**Next:** [Chapter 5 — Embeddings](05-embeddings.md), where text becomes
numbers.
