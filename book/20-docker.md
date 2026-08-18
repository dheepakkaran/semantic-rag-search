# Chapter 20 — Docker

**Files:** `python-service/Dockerfile`, `node-api/Dockerfile`, `web/Dockerfile`

## Why containers here

Not because containers are modern. Because this system has a specific problem:
**three runtimes.**

Python 3.11 with a 978 MB dependency tree. Node 20. nginx. Plus PostgreSQL and
MongoDB. Installing all of that on a laptop, then again on a server, then keeping
the versions matched, is exactly the work containers remove.

The test for whether it was worth it comes in Chapter 26: a bare Ubuntu instance
on AWS went from nothing to a running stack in about fifteen minutes, most of it
waiting for a build. Without containers that would have been an afternoon of
installing Python, Node, two databases and nginx by hand — and then discovering
the versions did not match the laptop.

## Three images

| Image | Size | Base |
|---|---|---|
| `web` | **76.2 MB** | `nginx:1.27-alpine` |
| `node-api` | **323 MB** | `node:20-slim` |
| `python-service` | **8.88 GB** | `python:3.11-slim` |

That last number is not a typo, and the rest of this chapter is largely about it.

## The two easy ones

Both Node images use a **multi-stage build**: compile in one image, copy the
result into a clean one.

```dockerfile
# Build stage: compile TypeScript with dev dependencies present.
FROM node:20-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY tsconfig.json ./
COPY src/ ./src/
RUN npm run build

# Run stage: production dependencies and compiled JavaScript only.
FROM node:20-slim
WORKDIR /app
ENV NODE_ENV=production
COPY package*.json ./
RUN npm ci --omit=dev
COPY --from=build /app/dist ./dist

EXPOSE 3001
CMD ["node", "dist/index.js"]
```

The build stage needs TypeScript, Vitest, type definitions — hundreds of
megabytes of tooling. None of that is needed to *run* the service.

`COPY --from=build /app/dist ./dist` takes only the compiled JavaScript. The
final image has production dependencies and output, and the toolchain is
discarded with the intermediate stage.

The web image goes further:

```dockerfile
FROM node:20-slim AS build
...
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY 40-resolver.sh /docker-entrypoint.d/40-resolver.sh
EXPOSE 80
```

Node builds the front end and then disappears entirely. The runtime image is
nginx plus a folder of static files — **76 MB**, and no JavaScript runtime in
production at all.

## The 8.88 GB one

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Dependencies first: this layer is cached until requirements.txt changes, so
# editing application code does not reinstall torch every build.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image. Without this the container downloads
# it on first request, which makes the first search look broken.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('all-MiniLM-L6-v2')"

COPY rag/ ./rag/
COPY app.py cli.py ./

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Where the size goes:

```
5.42 GB   RUN pip install --no-cache-dir -r requirements.txt
 93.2 MB  RUN python -c "...SentenceTransformer('all-MiniLM-L6-v2')"
 90.1 kB  COPY rag/ ./rag/
 20.5 kB  COPY app.py cli.py ./
```

**One layer is 5.42 GB.** That is PyTorch and its dependency tree, unpacked. The
978 MB measured in Chapter 2 was the installed size on a Mac; in a Linux image
with the CUDA-capable wheels it is larger still.

Your own code is 110 kilobytes of it.

## Two deliberate choices in that file

### Dependencies before code

```dockerfile
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY rag/ ./rag/          # ← code comes after
```

Docker caches each layer and invalidates everything after the first change. Copy
the code first and every one-character edit reinstalls PyTorch — eight minutes
per build.

With `requirements.txt` first, editing `retriever.py` invalidates only the last
two layers. Rebuild: a few seconds.

This ordering is the single highest-value habit in writing Dockerfiles.

### The model is baked in

```dockerfile
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('all-MiniLM-L6-v2')"
```

Constructing the model downloads it. Doing that at build time puts the 93 MB into
the image.

Without it, the download happens on the container's **first request** — the first
search after every deployment takes thirty seconds instead of four milliseconds
and looks broken. Worse, it needs network access at runtime, which a locked-down
environment may not have.

> **General principle: pay fixed costs at build time, not on the user's first
> request.**

## Why not `--no-cache-dir` everywhere else

```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
```

pip keeps downloaded wheels in a cache directory. Inside an image that cache is
dead weight — it is never reused, because the next build starts from the same
base layer.

`--no-cache-dir` skips it. Worth a few hundred megabytes on an image already
carrying too many.

## `.dockerignore`

```
venv/
__pycache__/
*.pyc
tests/
.pytest_cache/
```

Without this, `COPY` sends the entire directory to the Docker daemon first —
including the 978 MB `venv/` that would then be shadowed by the container's own
installation. Slow, and pointless.

`tests/` is excluded too. Tests run in CI (Chapter 25), not in the production
image.

The Node ones exclude `node_modules/` for the same reason — the image runs
`npm ci` itself, and copying the host's `node_modules` in would be both slow and
wrong, since the host is macOS and the image is Linux.

## The size is a real problem

8.88 GB is not just untidy. It has consequences that appear later in this book:

| Where | Consequence |
|---|---|
| **CI** (Chapter 25) | The image build job takes ~8 minutes, against ~1 for the others |
| **AWS** (Chapter 26) | The first build on a 2 GB instance needs swap or it is killed |
| **Serverless** | A cold start would pull 8.88 GB — minutes before the first response |
| **Registries** | Free tiers are typically 500 MB. This does not fit |

The fix is known and not done: `sentence-transformers` can run this model through
ONNX Runtime instead of PyTorch. Same vectors, same interface, and the image
drops to a few hundred megabytes.

It is not done because the deployment target — one VM running Compose — copes
fine. It would become necessary the moment the target was a serverless container
platform, and that is written down rather than left as a surprise.

**Naming the condition under which a decision flips is more useful than the
decision.**

## Build them

```bash
docker compose -f docker-compose.yaml build
```

First time: ten minutes or so, most of it PyTorch. After that, changing Python
code rebuilds in seconds because of the layer ordering above.

## What runs inside

```dockerfile
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

`--host 0.0.0.0`, not `127.0.0.1`. Inside a container, binding to localhost means
binding to the container's own loopback — nothing outside can reach it. This is a
common first-container mistake: the process starts, the logs look healthy, and
every connection is refused.

---

## What you should take from this chapter

| | |
|---|---|
| Why containers here | Three runtimes and two databases, twice |
| Multi-stage | Build with the toolchain, ship without it — 76 MB web image |
| Dependencies before code | Or every edit reinstalls PyTorch |
| Bake in fixed costs | The model downloads at build, not on first request |
| `0.0.0.0`, not localhost | Or nothing outside the container can connect |
| The 8.88 GB | Real consequences in CI, on AWS, and anywhere serverless |

---

**Next:** [Chapter 21 — Compose](21-compose.md), where five containers become one
command.
