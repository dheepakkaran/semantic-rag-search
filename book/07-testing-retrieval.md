# Chapter 7 — Testing retrieval

**Files:** `python-service/tests/test_chunker.py`, `tests/test_retrieval.py`

## The problem with testing this

Normal code has right answers. `add(2, 2)` is 4, and a test asserts exactly that.

Retrieval does not work like that. What is the correct similarity score for
*"how do I stop my network memorising?"* against a paragraph about dropout?

There isn't one. It depends on the model, the chunk boundaries, the wording. Swap
the embedding model and every number changes — while the system still behaves
correctly.

So this test is a trap:

```python
def test_similarity():
    hits = search_chunks(store, "how do I stop my network memorising?")
    assert hits[0].score == 0.412        # ← will break for no good reason
```

It passes today and fails the moment anything changes, telling you nothing about
whether the system got worse.

## What to assert instead

Test the properties that must hold regardless of the exact numbers.

| Property | Why it must hold |
|---|---|
| **Ordering** | The relevant document ranks above the irrelevant one |
| **Invariants** | Vectors are unit length; scores come back descending |
| **Boundaries** | Empty store, `k` bigger than the corpus, blank input |
| **Behaviour** | Deleting a document removes it from results |

None of these mention a specific score. All of them break if retrieval genuinely
breaks.

## A fixture that makes ordering testable

The trick is choosing test data where the right answer is obvious to a human but
requires real semantic matching from the machine.

```python
NOTES = {
    "training": (
        "Gradient descent nudges each weight against the slope of the loss. "
        "The size of that step is the learning rate."
    ),
    "overfitting": (
        "Weight decay penalises large weights and dropout switches off units "
        "at random, so the network cannot lean on a single path."
    ),
    "cooking": (
        "Heat the pan until a drop of water skitters across it, then add oil "
        "and let it shimmer before the onions go in."
    ),
}
```

Three documents. Two are about machine learning; one is about frying onions.

That third one is doing real work. It is an **unmistakable negative** — no
plausible bug makes a cooking instruction the best match for a question about
neural networks. If it ever ranks first, something is deeply wrong, and the test
will say so.

## The test that matters most

```python
def test_finds_the_right_document_without_sharing_any_keywords(store):
    # "regularisation", "dropout" and "weight decay" are all absent from the
    # question — a keyword search would return nothing here.
    hits = search_chunks(store, "how do I stop my network memorising?", k=1)
    assert hits[0].document_id == "overfitting"
```

This is the whole thesis of the project as a single assertion.

The question shares no meaningful vocabulary with the passage. If this passes,
semantic retrieval is working. If it fails, nothing downstream matters.

Note what it does *not* assert: no score, no threshold. Just — the right document
came first.

## The rest of the suite

```python
def test_empty_store_returns_nothing():
    assert search_chunks(InMemoryStore(), "anything") == []


def test_unrelated_question_ranks_the_unrelated_note_last(store):
    hits = search_chunks(store, "how big should the step size be?", k=3)
    assert hits[0].document_id == "training"
    assert hits[-1].document_id == "cooking"


def test_scores_come_back_in_descending_order(store):
    scores = [hit.score for hit in search_chunks(store, "learning rate", k=3)]
    assert scores == sorted(scores, reverse=True)


def test_k_is_capped_at_the_number_of_chunks(store):
    assert len(search_chunks(store, "anything", k=99)) == len(store)


def test_vectors_are_unit_length(store):
    _, vectors = store.load()
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)


def test_deleting_a_document_removes_it_from_results():
    s = InMemoryStore()
    for document_id, text in NOTES.items():
        s.add(document_id, text)

    assert s.delete_document("overfitting") == 1
    found = {hit.document_id for hit in search_chunks(s, "dropout weight decay", k=5)}
    assert "overfitting" not in found
```

`test_vectors_are_unit_length` is the quiet one worth keeping. Chapter 6's entire
simplification depends on unit vectors. If someone removes
`normalize_embeddings=True`, retrieval still runs and still returns plausible
results — the scores are just subtly wrong. That is the worst kind of bug: no
crash, no error, only slightly degraded output. This test catches it immediately.

## Testing the chunker

The chunker has no model in it, so it can be tested exactly.

```python
def test_chunks_overlap_by_the_requested_amount():
    words = [str(n) for n in range(300)]
    chunks = chunk_text(" ".join(words), size=100, overlap=20)

    first, second = chunks[0].split(), chunks[1].split()
    # The window advanced by size - overlap = 80 words...
    assert second[0] == "80"
    # ...so the last 20 words of chunk 1 are the first 20 of chunk 2.
    assert first[-20:] == second[:20]
```

Using numbers as the words is a small trick that pays off. `chunks[1]` starting
at `"80"` is directly readable — with real prose you would be squinting at text
trying to work out where you were.

```python
def test_every_word_appears_somewhere():
    words = [str(n) for n in range(500)]
    chunks = chunk_text(" ".join(words), size=120, overlap=20)
    seen = {word for chunk in chunks for word in chunk.split()}
    assert seen == set(words)
```

This one guards against the worst possible chunker bug: silently dropping text.
A document with a missing paragraph produces an answer that is confidently wrong
about something you *did* write down, and nothing anywhere reports an error.

```python
def test_no_trailing_chunk_that_repeats_covered_words():
    # 260 words with a 300-word window: the first window already covers
    # everything, so a second one would be pure duplication.
    text = " ".join(["word"] * 260)
    assert len(chunk_text(text, size=300, overlap=50)) == 1
```

This is the `break` from Chapter 4, pinned down. Without it the function returns
two chunks, the second entirely contained in the first.

## The fixture that makes it fast

```python
@pytest.fixture(scope="module")
def store():
    s = InMemoryStore()
    for document_id, text in NOTES.items():
        s.add(document_id, text)
    return s
```

`scope="module"` builds the store once for the whole file rather than once per
test. The embedding model loads once instead of seven times, and the suite goes
from about thirty seconds to about five.

The trade is that tests share state. That is safe here because every test using
this fixture only reads. The one test that mutates —
`test_deleting_a_document_removes_it_from_results` — builds its own store, which
is why it does not take the fixture.

Getting this wrong is a classic source of tests that pass alone and fail
together.

## What running it looks like

```bash
cd python-service
./venv/bin/python -m pytest -q
```

```
.........................                                        [100%]
25 passed in 5.04s
```

Five seconds, no network, no API key, no cost. That is the standard to hold: a
suite that is slow or expensive is a suite people stop running.

## The bug this chapter found

> **What went wrong**
>
> Everything above passed locally. Then CI, which runs a bare `pytest` rather
> than `python -m pytest`, failed:
>
> ```
> ModuleNotFoundError: No module named 'rag'
> ```
>
> `python -m pytest` adds the current directory to `sys.path`. The `pytest`
> launcher does not. So `import rag` resolved locally and not in CI.
>
> The fix, in `pytest.ini`:
>
> ```ini
> [pytest]
> testpaths = tests
> # Without this, `pytest` (as opposed to `python -m pytest`) does not put the
> # service root on sys.path and `import rag` fails. CI runs the bare command.
> pythonpath = .
> ```
>
> This was caught before pushing, by deliberately running the suite the way CI
> would rather than the way that was convenient.

There is a general lesson in it. **Run things the way production runs them, not
the way that is comfortable.** The same principle turns up again in Chapter 22,
where a container works under Compose and fails on Kubernetes for an almost
identical reason: an implicit default that differed between environments.

---

## What you should take from this chapter

| | |
|---|---|
| Do not assert scores | They change with the model and mean nothing alone |
| Assert ordering | The right document ranks above the wrong one |
| Assert invariants | Unit length, descending order, `k` capped |
| Include an obvious negative | The cooking note that must never win |
| Keep it free | No network, no key, no cost — or it stops being run |

---

**Next:** [Chapter 8 — Grounding](08-grounding.md), where we start the second
half of RAG and make a model answer only from what we give it.
