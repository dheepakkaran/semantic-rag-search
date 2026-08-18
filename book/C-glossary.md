# Appendix C — Glossary

Every term this book uses, defined the way it is actually used here rather than
the way a dictionary would.

---

## Retrieval and embeddings

**RAG — Retrieval-Augmented Generation.** Find the relevant passages first, then
ask a language model to answer *using only those*. The retrieval half is what
lets the answer cite sources and what stops the model inventing things.

**Chunk.** A slice of a document, here 120 words with a 20-word overlap. The unit
that gets embedded, stored, retrieved and cited. → Chapter 4

**Overlap.** Words repeated between neighbouring chunks, so a sentence split
across a boundary still appears whole in one of them.

**Embedding.** A list of numbers representing a piece of text, arranged so that
texts with similar meaning have similar numbers. Here, 384 of them per chunk.
→ Chapter 5

**Vector.** The embedding, seen as a point in 384-dimensional space.

**`all-MiniLM-L6-v2`.** The embedding model used throughout. 22 MB, runs on CPU,
produces 384-dimensional vectors. Small and old by current standards, and
entirely adequate for this.

**Cosine similarity.** How close two vectors point in the same direction, from
-1 to 1. The similarity measure used for ranking.

**Unit-normalised.** Scaled to length 1. Once both vectors are unit-normalised
their dot product *is* the cosine similarity, which is why ranking here is a
single matrix multiply. → Chapter 6

**Dot product.** Multiply matching elements, add up the results. `vectors @
query_vector` does it for every chunk at once.

**Linear scan.** Comparing the query against every chunk rather than using an
index. Rejected wisdom, measured to be right at this size: 0.08 ms for 5,000
chunks. → Chapter 19

**top-k.** The k highest-scoring chunks. Here k = 4.

**`argsort`.** NumPy's "give me the indices that would sort this". `[::-1]`
reverses it to highest-first.

**Vector database.** A store with an index built for nearest-neighbour search —
Pinecone, Chroma, pgvector. Deliberately not used here; Chapter 19 explains at
what size that stops being defensible.

**Grounding.** Constraining an answer to supplied text. The instruction *"use
only the notes below"* plus the passages themselves.

**Citation.** The `[1]`, `[2]` markers tying a sentence in the answer to a
retrieved passage.

**Hallucination.** A model stating something not in its sources and not true.
Grounding plus visible citations is the defence here — not because the model
cannot do it, but because you can see when it has.

---

## The services

**FastAPI.** The Python web framework running the retrieval and generation
service. Validates request bodies from type hints via Pydantic.

**Pydantic.** Python data validation from type annotations. A wrong type in a
request body becomes a 422 with a readable message, without a line of validation
code.

**uvicorn.** The server that actually runs the FastAPI app.

**Express.** The Node web framework serving the API the browser talks to.

**Vite.** The build tool for the React app. Dev server with instant reload;
`build` produces static files for nginx.

**nginx.** Serves the built frontend and proxies `/api` to the Node service.
Also where the rate limit lives, because it is already in front of everything.
→ Chapters 18, 22

**Reverse proxy.** A server that receives requests and forwards them to another
server. nginx, here.

---

## The stores

**PostgreSQL.** Relational database holding document metadata — id, title,
created time. Chosen because that data has relationships and gets joined.

**MongoDB.** Document store holding chunks and their vectors. Chosen because a
chunk is a blob of text plus an array of floats and has no relationships.

**Compensating delete.** Two stores cannot share a transaction, so if embedding
fails after the metadata row is written, the row is deleted to undo it.
Best-effort — a crash between the steps still leaves an inconsistency. → Chapter 12

**In-memory store.** A store implementation holding everything in Python
variables. Selected automatically when `MONGO_URI` is unset, which is what lets
the service and its tests run with no database at all.

---

## The model layer

**Provider.** A source of generated text — `gemini`, `openai`, `ollama`, `mock`.
All behind one function, so swapping one is an environment variable. → Chapter 9

**Provider chain.** An ordered list. If one refuses in a way worth retrying, the
same prompt goes to the next. → Chapter 17

**Retryable.** A failure about the *provider* rather than the request — 429, 503,
500. Worth trying elsewhere. A 401 or 400 is not: it will fail identically
everywhere.

**Quota.** The provider's usage allowance. Gemini's free tier: 20 generations per
day.

**Mock provider.** Returns a fixed string without calling anything. Makes the
whole system demonstrable offline and keeps tests free.

**Ollama.** Runs language models locally. The zero-network, zero-cost option in
the chain.

**Prompt.** The text sent to the model — the instructions, the retrieved
passages, and the question.

**Token.** The unit models count in, roughly ¾ of a word. What paid providers
bill on.

---

## Containers

**Image.** A packaged filesystem plus the command to run. Built once, run
anywhere.

**Container.** A running instance of an image.

**Layer.** One step of a Dockerfile. Cached, so an unchanged step is reused —
which is why dependencies are installed before source is copied. → Chapter 20

**Multi-stage build.** Build in one image with the full toolchain, copy only the
output into a smaller final image. How the web image ends up as nginx plus static
files rather than nginx plus Node plus `node_modules`.

**`.dockerignore`.** Files excluded from the build context. Keeping `node_modules`
and `venv` out is worth seconds on every build.

**Docker Compose.** Runs several containers together from one YAML file.

**Override file.** `docker-compose.override.yml`, applied automatically on top of
the base file. How dev gets bind mounts and prod does not. → Chapter 21

**Healthcheck.** A command the daemon runs periodically to decide whether a
container is healthy. `depends_on: condition: service_healthy` waits for it.

**Bind mount.** A host directory mapped into a container, so editing a file on
your Mac changes it inside. Development only.

**Volume.** Storage managed by Docker that survives `down`. Where Postgres and
Mongo keep their data.

---

## Kubernetes

**Pod.** The smallest unit — one or more containers scheduled together.

**Deployment.** Declares how many pods of something should exist and keeps that
true.

**ReplicaSet.** What a Deployment creates to hold the pods at the requested
count.

**Service.** A stable name and address in front of a set of pods, load-balancing
between them.

**ClusterIP.** A Service reachable only inside the cluster. The default.

**NodePort.** A Service also reachable on a port of the node itself. How you
reach the app from your browser with minikube.

**ConfigMap.** Non-secret configuration as key/value pairs, injected as
environment variables.

**Secret.** The same, for values that should not be in the repository.
Base64-encoded, which is encoding rather than encryption.

**Liveness probe.** *Is this container wedged?* Failing it restarts the
container.

**Readiness probe.** *Can this container take traffic yet?* Failing it removes
the pod from the Service without restarting it. Confusing the two causes restart
loops during slow start-up. → Chapter 23

**`emptyDir`.** Storage tied to the pod's lifetime. Used here for the databases,
which is why Kubernetes data does not survive a restart — and why that is in the
honest-limits list.

**`ImagePullBackOff`.** Kubernetes cannot find the image. Almost always a typo in
the name or an image that was built into the wrong Docker daemon.

**CoreDNS.** The cluster's DNS, at `10.96.0.10`. Not `127.0.0.11`, which is
Docker's — a distinction that cost a debugging session. → Chapter 24

**FQDN.** The full name, `node-api.default.svc.cluster.local`. Needed because
nginx's resolver does not apply search domains.

**minikube.** A single-node Kubernetes cluster on your laptop.

**`kubectl`.** The command-line client for talking to a cluster.

---

## Deployment and operations

**Lightsail.** AWS's simplified virtual server product. Fixed monthly price,
firewall and networking included. **Bills stopped instances** — see Chapter 27.

**Instance.** The virtual machine.

**Static IP.** An address that survives a restart. Free while attached, billed
while not.

**Swap.** Disk used as overflow memory. Two gigabytes of it is what lets a 2 GB
instance build the PyTorch image.

**Snapshot.** A stored copy of the instance's disk. About $0.25/month here, and
the cheap way to pause.

**Budget alert.** An email when spend crosses a threshold. Created before the
instance, not after.

**Idempotent.** Safe to run twice. `setup.sh` is; that is why the recovery
instruction is "run it again".

**Seed.** Loading the starting documents so the app is not empty on first visit.

**Runbook.** The written procedure for operating the thing — `deploy/RUNBOOK.md`.

---

## Testing and CI

**CI — Continuous Integration.** Tests run automatically on every push. Four jobs
here, none of which needs a secret. → Chapter 25

**GitHub Actions.** GitHub's CI. Configured in `.github/workflows/`.

**Fixture.** Reusable test setup. pytest's `@pytest.fixture`.

**`monkeypatch`.** pytest's tool for temporarily replacing a function or
environment variable, undone automatically afterwards.

**Mock.** A stand-in for a real dependency. `_call` is mocked so the fallback
tests never touch a network.

**p50 / p95.** The median and the 95th percentile. Reported instead of the mean,
because an average hides both the typical case and the slow one.

**Warm-up call.** A discarded first run, so that one-time costs like model
loading do not land in the measurement.

---

## Frontend

**React.** The UI library. Components are functions; state changes re-render.

**Hook.** `useState`, `useEffect` — React's way of giving a function component
state and side effects.

**TypeScript.** JavaScript with types, checked at build time.

**`aria-live`.** Tells a screen reader to announce a region when it changes.
`polite` waits for a pause; `assertive` interrupts.

**`role="alert"`.** Announced immediately. Used for errors.

**`aria-hidden`.** Hides an element from screen readers. Correct for the score
bar, which repeats a number already beside it; wrong for anything carrying unique
information.

**`:focus-visible`.** Shows a focus ring for keyboard users and not mouse users.
The right answer to the old habit of `outline: none`.

**WCAG.** The accessibility guidelines. AA requires 4.5:1 contrast for normal
text, 3:1 for large text and for control boundaries. → Chapter 16

**Contrast ratio.** From 1:1 to 21:1. Three values in this project failed and all
three looked fine.

---

## HTTP

**429 Too Many Requests.** Rate limited, or out of quota.

**422 Unprocessable Entity.** The request was understood but the data is wrong.
FastAPI's response to a validation failure.

**502 Bad Gateway.** A proxy could not reach what it was proxying to. Chapter 22's
symptom.

**503 Service Unavailable.** Temporarily down or overloaded. Also what this system
uses internally for "that provider has no key".

**CORS.** The browser rule about which origins may call which. Not an issue here
because nginx serves the frontend and proxies the API from the same origin.

**`limit_req_zone`.** nginx's rate limit. Counters live in one process's shared
memory, which is why the limit weakens as replicas multiply.

**Resolver.** nginx's DNS configuration. Without it, a `proxy_pass` hostname is
looked up once at start-up and cached forever — the cause of Chapter 22's 502.

---

**Back to the [table of contents](README.md).**
