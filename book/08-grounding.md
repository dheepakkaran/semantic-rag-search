# Chapter 8 — Grounding

**File:** `python-service/rag/pipeline.py`

## The second half begins

Retrieval works. Ask a question and the right passages come back, ranked.

You could stop here. A ranked list of three paragraphs is genuinely useful, and
this project keeps it as its own endpoint. But often the answer is spread across
those three paragraphs and you would rather have it in a sentence.

So: hand the passages to a language model and ask it to write that sentence.

The entire difficulty is in one word: **only**. The model must answer *only* from
the passages you gave it.

## Why "only" is hard

A language model already knows what dropout is. It read about it thousands of
times in training. Ask it about dropout and it will answer happily, whether or
not you supply any passages.

That is the failure mode. You build a RAG system, it produces a beautiful
answer, and you have no idea whether it came from your notes or from the model's
memory. If it came from memory, the citation you print beside it is a decoration.

So the prompt has to do real work.

## The prompt

```python
PROMPT = """Answer the question using only the notes below.
Cite the notes you use like [1] or [2].
If the notes do not contain the answer, say you do not know.
Write plain prose. Do not use markdown, bullet points or asterisks — the
answer is displayed as text, so any formatting shows up as literal symbols.

Notes:
{context}

Question: {question}
Answer:"""
```

Six instructions, and each one is there because of something that went wrong
without it.

### "using only the notes below"

Without this the model answers from training data. With it, the model mostly
does not. "Mostly" is honest — this is an instruction, not a guarantee, and a
determined model can still drift. Which is why the next line exists.

### "Cite the notes you use like [1] or [2]"

This converts an unverifiable claim into a verifiable one.

The passages go in numbered:

```python
context = "\n\n".join(
    f"[{number}] {hit.text}" for number, hit in enumerate(hits, start=1)
)
```

The model writes `[1]` and `[2]` into its answer. The interface shows the
numbered passages underneath. A reader can check any sentence against its source
in about two seconds.

There is a second effect that matters more than the first. Requiring a citation
makes ungrounded claims *awkward to write*. The model cannot cite a passage that
does not support the claim, so claims without support tend not to appear.

### "If the notes do not contain the answer, say you do not know"

This is the line people leave out, and it is the most important one.

A model with no acceptable way to fail will produce *something*. That is what
"hallucination" usually is — not malice, just a system with no exit. Give it a
permitted failure and it takes it.

## The test that proves it

```
Q: who won the 2019 cricket world cup?
A: I do not know.

based on:
  [1] score 0.046 — generalisation A model that has memorised its training...
```

The model knows this. England won. It is in the training data many times over.

But it is not in the notes, so the system says so. And look at the score: 0.046,
compared with 0.5–0.6 for a real match. Retrieval had nothing to offer and
generation correctly refused to invent.

> **Run this test on any RAG system you are shown.** Ask something the model
> certainly knows and the documents certainly do not contain. If you get a
> confident answer, the grounding is decorative.

This is also the single best thing to demonstrate in an interview. Everyone shows
the question that works. Almost nobody shows the question that should fail.

### The counterpart test

Grounding that refuses everything is not grounding, it is a broken system. So
check the other direction too:

```
Q: why do we hold out a validation set?

A: We hold out a validation set to see whether the model has learned anything
   general or if it has merely memorised the training set [1]. While loss on
   the training data indicates how well the model memorised, loss on unseen
   validation data reveals whether it learned the underlying general pattern
   [1]. This also makes it easy to spot overfitting when training loss falls
   while validation loss begins to climb [1].

based on:
  [1] score 0.569
```

Three sentences, three citations, all pointing at the passage that scored 0.569.
That is what working looks like.

### "Write plain prose. Do not use markdown…"

This line was not in the original prompt. It was added after seeing this in the
interface:

> **What went wrong**
>
> ```
> * **More data:** A larger, more varied training set makes memorisation
> harder and helps the model find the underlying pattern [2].
> * **Weight decay:** Adds a penalty for large weights so the model does
> not rely too heavily on any single input [2].
> ```
>
> The model returned markdown. The interface renders the answer as plain text,
> so the asterisks appeared literally. It looked broken.
>
> Two possible fixes: render markdown in the front end, or tell the model not to
> produce it. Rendering markdown means a new dependency for one field.
> Constraining the format is one line in a prompt that already exists.
>
> The one line won. The answer now reads as prose:
>
> ```
> You can stop your network from memorising by using regularisation
> techniques or by gathering more data [2, 3]. Regularisation methods
> include weight decay, which adds a penalty for large weights; dropout,
> which randomly switches off units during training...
> ```

The general point: **the prompt is part of the interface contract.** If the
display cannot render something, the prompt should not ask for it.

## Assembling it

```python
def ask(store, question, k=4, provider=None) -> Answer:
    hits = search_chunks(store, question, k)
    if not hits:
        return Answer("No documents have been ingested yet.", [])

    context = "\n\n".join(
        f"[{number}] {hit.text}" for number, hit in enumerate(hits, start=1)
    )
    result = generate(PROMPT.format(context=context, question=question), provider)

    return Answer(result.text, hits, result.provider, result.model, result.fallbacks)
```

Two things worth noticing.

**The empty-store check comes first.** With no documents there is nothing to
ground an answer in, so the model is never called. This saves a request, but more
importantly it means the system cannot produce an ungrounded answer when it has
no sources at all — the one case where a model would be *guaranteed* to answer
from memory.

There is a test pinning this down:

```python
def test_ask_with_nothing_ingested_says_so_without_calling_the_model(client, monkeypatch):
    def explode(prompt: str, provider=None):
        raise AssertionError("the model must not be called when there is nothing to cite")

    monkeypatch.setattr("rag.pipeline.generate", explode)
    body = client.post("/ask", json={"question": "anything"}).json()
    assert "No documents" in body["answer"]
```

The mock *raises* if it is called. The test passes only if generation never
happens.

**The hits come back with the answer.** Not just the text — the passages too. The
caller cannot show an answer without also having its sources to hand. That is
enforced by the return type rather than by discipline.

## How many passages?

`k=4` by default. The trade-off:

| k | Effect |
|---|---|
| Too small | The answer may be in passage 5 and you never sent it |
| Too large | More tokens, more cost, and relevant text buried among noise |

Four works for lecture notes at 120 words per chunk — roughly 500 words of
context, comfortable for any modern model. The API accepts `k` between 1 and 10
so a caller can adjust.

Like chunk size, this deserves measuring against a labelled set. There isn't one
here, so 4 is a considered default rather than an optimum, and the README says so.

## Where grounding still fails

Honest limits, because pretending otherwise is worse than the limits themselves.

**The instruction is not a guarantee.** Models sometimes blend a retrieved fact
with a remembered one. Citations make this detectable, not impossible.

**Retrieval failure looks like grounding failure.** If the right passage was
never retrieved, the model answers from four wrong passages and may say "I do not
know" about something your notes do cover. That is Chapter 3's split again — and
the reason `/search` exists separately is so you can check which half failed.

**No evaluation set.** "It says I do not know when it should" is an observation
across a handful of examples, not a measured rate.

---

## What you should take from this chapter

| | |
|---|---|
| The hard word | **only** — the model already knows the answer |
| Citations | Turn a claim into a checkable claim |
| "Say you do not know" | Gives the model a way to fail that is not inventing |
| The test | Ask something the model knows and the notes do not |
| The prompt is interface | If the display cannot render it, do not ask for it |

---

**Next:** [Chapter 9 — Providers](09-providers.md), where the model behind the
answer becomes a swappable choice.
