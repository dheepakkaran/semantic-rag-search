# Semantic RAG Search

Ask a question about your own notes. Get an answer built only from the
passages the system found — with those passages shown underneath it.

![Asking a question, waiting for the model, and reading the passages the answer was built from](docs/demo.gif)

*Recorded against the deployed instance. The wait for the model is shortened;
nothing else is.*

---

## 1. The problem

I have lecture notes. I want to ask them questions.

Keyword search does not work here, because **the words in a question are
almost never the words in the notes.**

> **My question:** "how do I stop my network memorising?"
>
> **The paragraph I want:** "...dropout randomly disables neurons during
> training, and weight decay penalises large weights..."

Not one important word is shared. `Ctrl+F` finds nothing. A search engine
built on keywords finds nothing.

The paragraph is still the right answer. The question and the paragraph *mean*
the same thing — they just do not *say* the same thing.

So the search has to work on meaning, not on words.

---

## 2. What I chose to build

A small RAG system that runs on one machine and answers from my own notes.

| In scope | Why |
|---|---|
| Search notes by meaning | The actual problem above |
| Answer questions from the notes | Search gives passages; I want a sentence |
| Always show the sources | An answer I cannot check is not useful |
| Run with no API key at all | Search should work offline and cost nothing |
| Swap the language model | I want to compare a local model with a hosted one |

| Out of scope | Why |
|---|---|
| A vector database | I measured it. Ranking is 2% of a query. [Section 7](#7-result-speed) |
| LangChain or any framework | The retrieval step is about 30 lines. A framework would hide them |
| Training or fine-tuning a model | Off-the-shelf embeddings already separate these passages |
| Multi-user accounts, login | It is my notes on my machine |
| Chat history, follow-up questions | One question, one answer. Adding memory is a different problem |

The out-of-scope list is the more useful one. Every line on it is something I
could have built and chose not to.

---

## 3. Where the ideas come from

I did not invent the approach. Five ideas came from elsewhere.

| # | Idea | Source | What I took, and what I changed |
|---|---|---|---|
| 1 | Retrieve first, then generate | *Retrieval-Augmented Generation* (Lewis et al., 2020) | The shape: find passages, put them in the prompt, generate. I did **not** train anything jointly like the paper does — my retriever and my generator never meet during training |
| 2 | Sentence embeddings for search | *Sentence-BERT* (Reimers & Gurevych, 2019) | The model family. I use `all-MiniLM-L6-v2`, a small 384-dimension model from that line. Chosen for size, not for score |
| 3 | Normalise, then dot product | Standard practice in vector search | I normalise every vector to length 1 at embedding time. Then cosine similarity **is** the dot product, so the whole ranking step is one matrix multiply |
| 4 | Chunk with overlap | Common RAG practice | I took the idea. I did **not** take anyone's numbers — I measured 300 / 120 / 60 words on my own notes and picked 120. [Section 6](#6-result-accuracy) |
| 5 | Config from the environment | *The Twelve-Factor App* | Every key, URL and port comes from an env var with a working default, so the service starts with nothing configured |

---

## 4. The solution

Four modules. Each one exists because of a specific problem.

### 4.1 Chunker

| | |
|---|---|
| **Problem** | A whole document is one bad answer. Embed 3,000 words into one vector and it means nothing in particular |
| **Solution** | Split into 120-word chunks with 20 words of overlap. The overlap stops a sentence being cut in half at a boundary |
| **Result** | A 500-word document becomes 5 chunks. Each one is about one thing |

### 4.2 Embedder

| | |
|---|---|
| **Problem** | Text cannot be compared by meaning. Numbers can |
| **Solution** | `all-MiniLM-L6-v2` turns each chunk into 384 numbers. Runs locally on the CPU, no API call |
| **Result** | Every vector has length exactly 1.0000 — measured, not assumed. That is what makes step 4.3 one line |

### 4.3 Retrieval

| | |
|---|---|
| **Problem** | Find the closest chunks to a question, fast, without adding a database |
| **Solution** | One matrix multiply over every chunk, then sort |
| **Result** | 0.08 ms for 5,000 chunks. A vector index would speed up 2% of the query |

```python
scores = vectors @ query_vector      # cosine, because both are unit length
best   = np.argsort(scores)[::-1][:k]
```

### 4.4 Generation

| | |
|---|---|
| **Problem** | A language model will happily answer from memory and sound confident doing it |
| **Solution** | Give it only the retrieved passages and tell it to say "I don't know" otherwise. Return the passages with the answer |
| **Result** | Every answer is checkable. The sources sit under it on screen |

```
Answer the question using only the notes below.
Cite the notes you use like [1] or [2].
If the notes do not contain the answer, say you do not know.
Write plain prose. Do not use markdown, bullet points or asterisks — the
answer is displayed as text, so any formatting shows up as literal symbols.
```

That last line is not style. It is there because the first real answer came
back full of `**asterisks**` rendered literally on the page.

### How they fit together

```
INGEST    document ──► chunk ──► embed ──► store

SEARCH    question ──► embed ──► dot product over all chunks ──► top 4

ASK       SEARCH ──► prompt ──► language model ──► answer + the 4 passages
```

The browser only ever talks to `node-api`. Seven routes, in three groups:

| | | |
|---|---|---|
| **The RAG core** | `GET /api/search?q=` | Ranked passages. No model called, no key needed |
| | `POST /api/ask` | A grounded answer, plus its sources |
| **Documents** | `GET /api/documents` | List what has been ingested |
| | `POST /api/documents` | Add notes — chunk, embed and store them |
| | `DELETE /api/documents/:id` | Remove a document and its chunks |
| **Service** | `GET /api/health` | Is it up |
| | `GET /api/providers` | Which models are configured, so the picker is not hard-coded |

The two in the first group are the interesting ones, and they are split on
purpose: **retrieval is useful without generation.** `search` calls no model,
so it needs no key and works with the network unplugged. `ask` is `search`
plus one more step.

---

## 5. How I built it

Eleven steps, in order. The third column is the one that matters: I did not
move on until I had something that told me the step actually worked.

| # | Step | How I knew it worked |
|---|---|---|
| 1 | Project scaffolding | Nothing to prove yet |
| 2 | The RAG core — chunk, embed, retrieve, generate | Asked "what stops a model memorising?" from a script. It returned the dropout paragraph, which shares no words with the question |
| 3 | Tests for chunking and retrieval | The suite grew to 36 tests, none of them touching a network or a model. Retrieval tested **separately** from generation, so a wrong answer has an obvious first question: did retrieval even hand over the right passage? |
| 4 | HTTP API with FastAPI | `curl` returned the same passages the script did |
| 5 | Node API with PostgreSQL for metadata | 12 tests with Postgres and the Python service both mocked |
| 6 | React + TypeScript front end | Asked a question in the browser and saw the answer with its four sources underneath |
| 7 | Containerised all three services | `docker compose up` on a clean checkout, then one question end to end |
| 8 | Kubernetes manifests | `minikube service web`, same question, same answer. This step found **three** bugs that Compose had hidden |
| 9 | CI on every push | A deliberately broken commit failed the build |
| 10 | Deploy script and runbook for AWS | Ran `setup.sh` on a blank Ubuntu box. It went from nothing to a working URL |
| 11 | Wrote the book | Explaining a decision in prose is the fastest way to find out I could not justify it |

Step 8 is the one I would keep if I could only keep one. Running the same code
in a second environment found more bugs than any other activity. See
[section 9](#9-what-broke).

---

## 6. Result: accuracy

I have one real accuracy measurement, and one honest gap. Both are below.

### What I measured: chunk size

Same document, same question (*"how does a model learn?"*), three settings:

| chunk size | chunks made | top score | right passage? |
|---|---|---|---|
| 300 words | 2 | 0.363 | Yes — but the chunk covers two unrelated topics |
| **120 words** | **5** | **0.404** | **Yes** |
| 60 words | 10 | 0.408 | **No** |

Read the last row carefully. At 60 words the **similarity score went up and
the answer went wrong.**

A 60-word chunk is too small to be about any one thing, so it matches lots of
questions a little bit. The score looks better and the retrieval is worse.

**The lesson: a higher score is not the goal. Getting the right passage is.**
This is why I picked 120 by measuring instead of copying a number from a blog
post.

### The gap: I have no labelled test set

I do not have a set of questions with known-correct passages, so I cannot tell
you a recall number for this system.

"It finds the right paragraph" is an observation over a handful of examples I
wrote myself. That is enough to catch something obviously broken. It is not
enough to claim a quality figure, and I am not going to present it as one.

Building that test set is [item 1 of what I would do next](#10-what-i-would-do-next).

---

## 7. Result: speed

Measured on an M-series MacBook, CPU only, with `deploy/bench.py`.

| chunks | embedding throughput | retrieval p50 | p95 |
|---|---|---|---|
| 500 | 570 chunks/s | 3.7 ms | 3.9 ms |
| 2,000 | 661 chunks/s | 3.8 ms | 4.3 ms |
| 5,000 | 666 chunks/s | 4.6 ms | 6.8 ms |

The corpus grew **ten times** and retrieval barely moved. Splitting one query
in two shows why:

```
at 5,005 chunks
  encoding the question   3.80 ms
  ranking every chunk     0.08 ms   ← 2% of the query
```

**This is my case for not adding a vector database.** The part an index makes
faster is 2% of the time. The other 98% is one forward pass through the
embedding model, which an index does not touch at all. A vector database here
would add a dependency, a container and a failure mode to save 0.08 ms.

**Where that argument stops being true.** A linear scan grows with the corpus.
An index does not. So it flips somewhere. At a million chunks the scan is the
bottleneck and I would be wrong. My claim is only that 5,000 chunks is nowhere
near that point.

### Startup

```
import the embedding library    3.35 s
load the model weights          2.08 s
──────────────────────────────────────
first query after a cold start  ~5.4 s

every query after that            15 ms
```

Loading is a one-time cost per process. A restart pays it once.

---

## 8. Result: running it

### Models

| | | |
|---|---|---|
| **Embeddings** | `all-MiniLM-L6-v2`, 384 dimensions | Local, CPU, no key. This is the part that must be free — every chunk of every document goes through it |
| **Generation** | `gemini-3.6-flash` | Hosted, free tier. This is where answer quality comes from |
| **Generation** | `openai` · `ollama` · `mock` | Same function behind them all. `ollama` is local; `mock` needs no network at all |

Embeddings local, generation hosted, and that split is deliberate: embedding
is a bulk one-time job, so spending API quota on it would be waste.

**Generation falls back automatically.** The Gemini free tier allows 20
generations a day. When it runs out, the retrieved passages are still perfectly
good — so the same prompt goes to the next provider in the chain instead of the
request failing:

```
LLM_PROVIDER_CHAIN=gemini,openai,ollama     try in this order
LLM_PROVIDER=gemini                         pin one, no fallback
```

Nothing is re-retrieved and nothing is re-embedded, so the fallback model sees
**exactly the same context** the first one did. A provider with no key is
skipped without being called.

### Footprint

```
peak memory        459 MB     python-service, model loaded
python deps        8 packages
node deps          4 runtime, 9 dev
containers         5          web · node-api · python-service · postgres · mongo
```

### API keys

**Search needs no key.** `GET /api/search` never calls a language model, so
the retrieval half of the system runs on a machine with no network.

Only `/api/ask` needs one, and only for the last step.

```bash
cp .env.example .env          # add GEMINI_API_KEY — free from aistudio.google.com
docker compose up --build
open http://localhost:8080
```

Or run the pipeline with no server, no database and no key:

```bash
cd python-service
python -m venv venv && ./venv/bin/python -m pip install -r requirements.txt

./venv/bin/python cli.py sample_notes.txt search "what stops a model memorising?"
LLM_PROVIDER=mock ./venv/bin/python cli.py sample_notes.txt ask "why hold out a validation set?"
```

Or on Kubernetes:

```bash
minikube start
eval $(minikube docker-env)
docker compose build
# Both keys are required: the pod spec references each one and neither is
# marked optional, so a missing key stops the container starting.
kubectl create secret generic rag-secrets \
  --from-literal=GEMINI_API_KEY=your-key \
  --from-literal=OPENAI_API_KEY=your-key-or-empty

kubectl apply -f k8s/
minikube service web
```

---

## 9. What broke

Sixteen bugs are written up in [Appendix A](book/A-bugs.md), in the order they
happened. These six taught me the most.

| # | What I saw | The actual cause | How it was found |
|---|---|---|---|
| 1 | `404 — this model is no longer available to new users` | The model I had hard-coded had been retired. Nothing in my code was wrong | Calling the **real** API. A mock would never have told me |
| 2 | Nothing. The page looked fine | `documents.map((document) => ...)` — `document` is also a browser global, so inside that callback it shadowed the DOM | Reading the code. No test would have caught it |
| 3 | Nothing. The page looked fine | Three colours failed WCAG contrast: 3.40:1, 1.64:1, 1.26:1 against minimums of 4.5 and 3.0 | **Measuring** instead of looking. It looked fine to me — that is exactly the problem |
| 4 | `502 Bad Gateway` after rebuilding one service | nginx resolves an upstream hostname **once at startup** and caches it. The rebuilt container came back on a new IP | Rebuilding a single service instead of the whole stack |
| 5 | `recv() failed (111: Connection refused) ... resolver: 127.0.0.11:53` | I had hard-coded Docker's internal DNS address. That address does not exist on Kubernetes | Running the same image in a **second environment** |
| 6 | Every container up. Every health check green. Site unreachable | `.env` had no `WEB_PORT`, so Compose used its default of 8080. The firewall only allowed 80 | Actually opening the URL. "Healthy" and "reachable" are different claims |

Counting how each was found:

| Found by | Count |
|---|---|
| Running it in a second environment | **6** |
| Calling a real service instead of a mock | 3 |
| Reading the code carefully | 3 |
| Measuring instead of looking | 1 |
| Ordinary debugging | 2 |

The top row is the finding. **Porting the system to Kubernetes found more bugs
than writing tests did** — not because the tests were bad, but because the
tests and the code shared my assumptions. A second environment did not.

---

## 10. What I would do next

In the order I would actually do them.

**1. Build a labelled evaluation set.** Twenty questions, each with the passage
that should be retrieved, written to share as few words as possible with the
passage. Then `recall@k` and MRR become real numbers, CI can fail when they
drop, and [section 6](#6-result-accuracy) stops having a hole in it. This is
first because everything below is a change I currently cannot prove helps.

**2. Cache the vectors in memory.** Right now they are reloaded from MongoDB on
every query. Fine at a few thousand chunks, wasteful past that — and the fix is
small, because the vectors are derived data that can always be rebuilt.

**3. Chunk on sentences, not whitespace.** Splitting on word count cuts
sentences in half. Sentence boundaries would make passages more readable to a
person and probably to the model. Item 1 would tell me whether "probably" is
true.

**4. Collapse the two databases into one.** PostgreSQL for metadata and MongoDB
for chunks means two stores that cannot share a transaction. If embedding fails
after the metadata row is written, I delete the row to compensate — which is a
best-effort patch, not a fix. A crash between the two steps still leaves an
inconsistency.

**5. Move rate limiting to the ingress.** The nginx limit lives in one
process's shared memory, so the real limit is `6r/m × replicas`. With one web
container, eight rapid requests give `200 200 200 200 429 429 429 429`. With two
replicas, all eight return `200` — each pod only saw half. A shared counter or
an ingress-level limit is the fix.

---

## Appendix: configuration

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER_CHAIN` | `gemini,openai,ollama` | Tried in order. A provider with no key is skipped |
| `LLM_PROVIDER` | — | Set instead of the chain to pin one provider with no fallback |
| `GEMINI_API_KEY` | — | Free tier, from AI Studio. 20 generations a day |
| `OPENAI_API_KEY` | — | Used when Gemini runs out |
| `WEB_PORT` | `8080` | What Compose publishes on. `80` on a server |
| `MONGO_URI` | unset | Unset means the in-memory store, so the service starts with no database |
| `DATABASE_URL` | `postgres://rag:rag@localhost:5432/rag` | |
| `RAG_SERVICE_URL` | `http://localhost:8000` | Where node-api finds python-service |

## Tests

```bash
cd python-service && ./venv/bin/python -m pytest -q     # 36 tests
cd node-api       && npm test                           # 12 tests
```

No test touches a database, a network or a language model. CI runs on every
push, and a suite that spends API quota or needs a live Postgres is a suite
people start skipping.

## The book

[**Building a RAG System From Scratch**](book/README.md) — the full write-up:
every decision, every measurement, and every bug in the order it happened.
