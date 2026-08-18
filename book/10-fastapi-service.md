# Chapter 10 — The first HTTP service

**File:** `python-service/app.py`

## From functions to a service

Everything so far is a Python library. `ask(store, "why?")` works from a script,
which is fine for a CLI and useless for a browser.

This chapter puts HTTP in front of it. Nothing about the retrieval or generation
changes — this is a translation layer, and keeping it thin is the point.

## Why FastAPI

| | |
|---|---|
| **Types become validation** | Declare `k: int` and a request with `k="four"` is rejected before your code runs |
| **Docs for free** | `/docs` renders an interactive page from the type hints |
| **Async when needed** | Not needed here, but no rewrite if it becomes so |

The first one carries most of the value. Input validation is where a lot of
handwritten API code goes wrong, and here it is a side effect of describing the
shape you wanted anyway.

## The endpoints

Three, matching the three things the system does:

```
POST /ingest        store a document's chunks and vectors
GET  /search        the retrieval half — which passages match?
POST /ask           the full round trip, with a grounded answer
```

Plus two for operations:

```
GET    /health              chunk count and the provider chain
DELETE /documents/{id}      drop a document's chunks
```

`/search` and `/ask` being separate is the design decision from Chapter 3 made
concrete. `/search` never calls a model, so it costs nothing and works with no
API key. When an answer looks wrong, hitting `/search` with the same question
tells you immediately whether retrieval was the problem.

## Describing a request

```python
class AskRequest(BaseModel):
    question: str
    k: int = Field(default=4, ge=1, le=10)
    provider: str | None = None
```

Three lines, and they give you:

- `question` required; a request without it gets a 422 naming the missing field
- `k` optional, defaulting to 4, and **must** be between 1 and 10
- `provider` optional

Try to break it:

```python
def test_k_outside_the_allowed_range_is_rejected(client):
    assert client.post("/ask", json={"question": "x", "k": 0}).status_code == 422
    assert client.post("/ask", json={"question": "x", "k": 50}).status_code == 422
```

Both rejected, and no code in `ask_question` checks `k`. The bounds are in the
declaration.

Why bound it at all? `k=1000` would put a thousand passages in a prompt — slow,
expensive, and likely over the model's context limit. A bound turns a
possibly-expensive mistake into an immediate, cheap error.

## What validation does not catch

```python
if not request.question.strip():
    raise HTTPException(status_code=400, detail="question is empty")
```

`question: str` accepts `"   "`. It is a string. Pydantic is satisfied.

Whitespace-only input is a real case — someone hits Enter on an empty box — and
it needs a real answer, not an embedding of three spaces. So there is an explicit
check, and it returns **400** rather than 422 because this is a semantic
complaint about a well-formed request, not a shape error.

Small distinctions like that are what make an API pleasant to consume.

## The bug worth the whole chapter

Everything above is routine. This part is not.

Here is the original `/ask` handler:

```python
@app.post("/ask", response_model=AskResponse)
def ask_question(request: AskRequest) -> AskResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question is empty")

    answer, hits = ask(store, request.question, request.k)
    return AskResponse(...)
```

It reads fine. It passed its tests. It ran for hours.

Then the Gemini free tier ran out.

> **What went wrong**
>
> The browser showed:
>
> ```
> Internal Server Error
> ```
>
> The container log showed the truth:
>
> ```
> google.genai.errors.ClientError: 429 RESOURCE_EXHAUSTED.
> 'You exceeded your current quota... limit: 20,
>  model: gemini-3.6-flash. Please retry in 34.476147438s'
> ```
>
> The provider said, precisely and helpfully, *"you are out of quota, try again
> in 34 seconds."* By the time that reached the user it had become **500
> Internal Server Error** — which means "this service has a bug."
>
> It does not have a bug. It has a quota. Those need completely different
> responses from whoever is reading the message: one means wait a minute, the
> other means go and read a stack trace.

### Why it happened

`ask()` raised `LLMError`. Nothing caught it. FastAPI's default behaviour for an
unhandled exception is a 500 — correct in general, wrong here, because this
exception was carrying a status code the whole time.

### The fix

```python
    try:
        result = ask(store, request.question, request.k, request.provider)
    except LLMError as exc:
        # Pass the provider's own status through. A 429 for an exhausted quota
        # is something the caller can wait out; reporting it as a 500 tells
        # them to look for a bug that is not there.
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    except RuntimeError as exc:
        # Raised when the chosen provider has no API key configured.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
```

Now:

```
HTTP 429
{"detail": "429 RESOURCE_EXHAUSTED... Please retry in 34.476147438s"}
```

The status code survives the trip, and so does the retry delay.

### The tests that keep it fixed

```python
def test_provider_quota_error_keeps_its_status(client, monkeypatch):
    """A 429 from the provider must not surface as a 500.

    The free tier allows 20 generations a day, so this is the failure a user
    actually meets. Telling them the service is broken sends them looking for
    a bug instead of waiting a minute.
    """
    def out_of_quota(prompt: str, provider=None):
        raise LLMError(429, "429 RESOURCE_EXHAUSTED. Quota exceeded, retry in 34s")

    monkeypatch.setattr("rag.pipeline.generate", out_of_quota)
    client.post("/ingest", json={"document_id": "embeddings", "text": NOTES})

    response = client.post("/ask", json={"question": "how is nearness measured?"})

    assert response.status_code == 429
    assert "Quota exceeded" in response.json()["detail"]
```

This is exactly the kind of path that is easy to regress and impossible to notice
until the quota runs out again — probably during a demo. So it gets a test with a
docstring explaining why it exists.

### The general principle

> **An error that crosses a boundary should keep its meaning.**

Every layer that swallows a status code and substitutes a generic one destroys
information the next layer needed. It happens again in Chapter 13, where the Node
service initially wrapped this service's JSON error inside its own — producing a
JSON document nested inside another JSON document, with the useful sentence
buried two levels down.

Same mistake, different layer.

## Testing an API without a model

```python
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    import app as application
    from rag import InMemoryStore

    # A fresh store per test, so one test's documents cannot leak into another.
    application.store = InMemoryStore()
    return TestClient(application.app)
```

Two things happen here.

**The provider becomes `mock`.** No key, no network, no cost.

**The store is replaced per test.** `app.py` creates a module-level store at
import time. Without this line, a document ingested by one test would still be
there in the next, and tests would pass or fail depending on the order they ran
in. That class of bug is miserable to track down; one line prevents it.

For tests that need to inspect the prompt, generation is patched directly:

```python
def fake_generate(prompt: str, provider=None):
    seen["prompt"] = prompt
    return Generation("Cosine similarity, which is a dot product [1].", "mock", "mock")

monkeypatch.setattr("rag.pipeline.generate", fake_generate)
...
assert "[1] Cosine similarity compares" in seen["prompt"]
assert "only the notes below" in seen["prompt"]
```

That last pair of assertions is checking something real: **the retrieved passage
was actually put in front of the model, numbered, with the grounding
instruction.** Chapter 8's promise, verified rather than assumed.

## The store as a module-level global

```python
app = FastAPI(title="Semantic RAG Search — retrieval service")
store = build_store()
```

A global. Deliberately.

The store holds the embedding model and, in the in-memory case, all the vectors.
Creating one per request would reload a 22 MB model every time. One per process
is correct.

The cost is that tests must replace it, which the fixture does. That is a fair
trade, and it is written down rather than discovered.

## Health

```python
@app.get("/health")
def health() -> dict:
    """Used by Docker Compose and the Kubernetes readiness probe."""
    return {"status": "ok", "chunks": len(store), "chain": chain()}
```

Three fields, each earning its place:

- `status` — the thing orchestrators check
- `chunks` — has anything been ingested? Answers "why does search return
  nothing?" without opening a database
- `chain` — which providers are configured, in order. Answers "why is it using
  OpenAI?" instantly

A health endpoint that returns only `{"status": "ok"}` is a missed opportunity.
It is the one URL you can always reach; make it tell you something.

## Seeing it run

```bash
cd python-service
./venv/bin/python -m uvicorn app:app --reload --port 8000
```

Then open `http://localhost:8000/docs`. FastAPI has generated an interactive page
from the type hints — every endpoint, every field, with a button to try it.

That page is worth showing to anyone who asks what you built. It took no work.

---

## What you should take from this chapter

| | |
|---|---|
| Types as validation | `Field(ge=1, le=10)` replaces handwritten checks |
| 400 vs 422 | Well-formed but meaningless, versus wrong shape |
| **The big one** | An error crossing a boundary should keep its status |
| Test isolation | Replace module-level state per test, or tests couple |
| Health endpoints | The one URL always reachable — make it informative |

---

**Next:** [Chapter 11 — Two databases, one system](11-two-databases.md), where
the storage gets a second engine and an honest justification.
