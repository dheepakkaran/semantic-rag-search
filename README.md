# Semantic RAG Search

Ask a question about your own notes and get an answer built only from the
passages the system retrieved — with those passages shown underneath it.

Keyword search fails on notes because the words in a question are rarely the
words in the source. Asking *"how do I stop my network memorising?"* should
find the paragraph about dropout and weight decay, and it does — none of those
words appear in the question.

![The answer, with the passages it was built from underneath](docs/ui-answer.png)

<details>
<summary>More screenshots</summary>

Before asking anything:

![The empty state](docs/ui-hero.png)

Managing the notes that get searched:

![The notes panel](docs/ui-notes.png)

</details>

## What it does

Two endpoints, because retrieval and generation are separately useful:

| | |
|---|---|
| `GET /api/search?q=` | the retrieval half — ranked passages, no model called |
| `POST /api/ask` | the full round trip — a grounded answer plus its sources |

## How it works

```
chunk  ──►  embed  ──►  store                          ingest
query  ──►  embed  ──►  cosine similarity  ──►  top-k  retrieval  ("R")
top-k  ──►  prompt  ──►  language model                generation ("AG")
```

Retrieval is one matrix multiply. Both the chunk vectors and the query vector
are normalised to unit length, so their dot product *is* the cosine similarity:

```python
scores = vectors @ query_vector
best   = np.argsort(scores)[::-1][:k]
```

Generation is a prompt that constrains the model to the retrieved text:

```
Answer the question using only the notes below.
Cite the notes you use like [1] or [2].
If the notes do not contain the answer, say you do not know.
```

## Architecture

```
web (React + TypeScript)
  │  /api
node-api (Express + PostgreSQL)      ── document metadata, titles for citations
  │  HTTP
python-service (FastAPI + MongoDB)   ── chunking, embeddings, retrieval, generation
```

Three services, because two languages each do what they are better at: Python
owns the embedding model and the vector maths, Node owns the web layer and the
relational data. The split is also why the API surface stays small — the Node
service is the only thing the browser talks to.

## Decisions, and why

| Decision | Reason |
|---|---|
| NumPy, not a vector database | Ranking 5,000 chunks takes 0.08 ms — 2% of a query. [Measured below.](#performance) |
| No LangChain | Writing the retrieval step directly is ~30 lines and leaves nothing hidden behind an abstraction. |
| Embeddings local, generation hosted | Embedding is a bulk one-time job — no reason to spend API quota on it. Generation is where answer quality actually comes from. |
| PostgreSQL **and** MongoDB | Document metadata is relational and gets joined against results. Chunks are variable-length text plus a vector, with no relationships — a document store fits better. |
| Provider behind one function | Lets a local 3B model and a hosted model be compared on identical retrieved passages, and lets the demo run with no network. |
| Chunks 120 words, 20 overlap | Measured, not guessed — see below. |

### Chunk size was measured

Same document, same question (*"how does a model learn?"*), three settings:

| size | chunks | top score | right passage? |
|---|---|---|---|
| 300 | 2 | 0.363 | yes, but the chunk spans two unrelated topics |
| **120** | **5** | **0.404** | **yes** |
| 60 | 10 | 0.408 | **no** |

At 60 words the score went *up* and the answer went *wrong*: a chunk that
small no longer holds enough context to be about any one thing. A higher
similarity score is not the goal — retrieving the right passage is.

## Performance

Measured on an M-series MacBook, CPU only, with `deploy/bench.py`.

| chunks | embedding throughput | retrieval p50 | p95 |
|---|---|---|---|
| 500 | 570 chunks/s | 3.7 ms | 3.9 ms |
| 2,000 | 661 chunks/s | 3.8 ms | 4.3 ms |
| 5,000 | 666 chunks/s | 4.6 ms | 6.8 ms |

Retrieval barely moves as the corpus grows tenfold, and the reason is visible
when a single query is split in two:

```
at 5,005 chunks
  encoding the question   3.80 ms
  ranking every chunk     0.08 ms   ← 2% of the query
```

**This is the case for not adding a vector database.** The part an index would
speed up is 2% of the latency; the other 98% is one forward pass through the
embedding model, which an index does not touch. At this corpus size a vector
database would add a dependency, a container and a failure mode in exchange for
saving 0.08 ms.

That argument has a limit. The comparison is linear scan against an index, so
it flips somewhere — the dot product grows with the corpus while an index does
not. At a million chunks the scan is the bottleneck and the answer changes.
The claim here is only that 5,000 is nowhere near that point.

Embedding is a one-off cost per document at roughly 660 chunks/s, so a
50-page document takes about a second. The 500-chunk row understates it
slightly because the model load is included in the first run.

## Running it

### Everything, in containers

```bash
cp .env.example .env          # add GEMINI_API_KEY (free: aistudio.google.com)
docker compose up --build
open http://localhost:8080
```

### Just the pipeline, no server and no database

```bash
cd python-service
python -m venv venv && ./venv/bin/python -m pip install -r requirements.txt

./venv/bin/python cli.py sample_notes.txt search "what stops a model memorising?"
LLM_PROVIDER=mock ./venv/bin/python cli.py sample_notes.txt ask "why hold out a validation set?"
```

`search` never calls a language model, so it needs no key at all.

### On Kubernetes

```bash
minikube start
eval $(minikube docker-env)                       # build into minikube's daemon
docker compose build

kubectl create secret generic rag-secrets --from-literal=GEMINI_API_KEY=your-key
kubectl apply -f k8s/
minikube service web
```

## Tests

```bash
cd python-service && ./venv/bin/python -m pytest -q     # 23 tests
cd node-api       && npm test
```

No test touches a database, a network or a language model — the Python tests
use the in-memory store with `generate()` patched out, and the Node tests mock
both PostgreSQL and the retrieval service. That is deliberate: CI runs on every
push, and a suite that spends API quota or needs a live Postgres is a suite
people start skipping.

Retrieval is tested separately from generation, which matters more than it
looks. When an answer comes out wrong the first question is always *did
retrieval hand the model the right passage at all* — and these tests answer it
without involving a model.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` · `openai` · `ollama` · `mock` |
| `GEMINI_API_KEY` | — | free tier, from AI Studio |
| `MONGO_URI` | unset | unset ⇒ in-memory store, so the service starts with no database |
| `DATABASE_URL` | `postgres://rag:rag@localhost:5432/rag` | |
| `RAG_SERVICE_URL` | `http://localhost:8000` | where node-api finds python-service |

## Honest limits

- **Vectors are reloaded from MongoDB on every query.** Fine into the low
  thousands of chunks; past that this needs an in-process cache or a real
  vector index. Neither is worth adding for a personal notes collection.
- **The two stores cannot share a transaction.** If embedding fails after the
  metadata row is written, the row is deleted to compensate. That is a
  best-effort fix, not a real one — a crash between the two steps still leaves
  an inconsistency.
- **The Kubernetes manifests use `emptyDir`,** so database contents do not
  survive a pod restart. Real persistence needs StatefulSets with
  PersistentVolumeClaims, which assume a storage class.
- **Retrieval quality is not measured.** There is no labelled question/passage
  set here, so "it finds the right paragraph" is an observation on a handful of
  examples, not a number.
- **Chunking splits on whitespace,** ignoring sentence and paragraph
  boundaries. Splitting on sentences would keep passages more readable.
- **Answer quality depends entirely on the provider.** The local 3B model
  follows the "only use these notes" instruction noticeably less reliably than
  the hosted one.
