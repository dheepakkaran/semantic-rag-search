# Building a RAG System From Scratch

**A hands-on account of building one real project — from an empty folder to a
live URL on AWS.**

---

## Who this is for

You can write Python and you have seen a bit of JavaScript. You have heard of
RAG, Docker and Kubernetes, and you would like to actually build something with
them rather than read about them.

You do not need to know what an embedding is. You do not need a GPU. Everything
here runs on a laptop, and the deployment costs about three dollars a month.

## What makes this different from a tutorial

Most tutorials show you the path that worked. This book shows the path that
actually happened.

Every bug in here is one the project really hit, with the real error message and
the real fix. When a decision had a number behind it, the number is here, along
with the script that produced it. When something was left out — a vector
database, LangChain, a second cloud — the reason is here too.

That matters more than it sounds. The interesting part of engineering is rarely
the happy path. It is the moment nginx returns `502` after a redeploy and you
have to work out why, or the moment a free-tier quota runs out mid-demo and the
error says `500 Internal Server Error` when it should say `429`.

## What you will build

A search over your own notes that understands what you mean.

Ask *"how do I stop my network memorising?"* and it finds the paragraph about
dropout and weight decay — even though none of those words appear in your
question. Then it answers from that paragraph, and shows you the paragraph so
you can check it.

By the end it runs as five containers, on your laptop, on a Kubernetes cluster,
and on a public URL on AWS.

```
web (React + TypeScript)
  │  /api
node-api (Express + PostgreSQL)      ── document metadata
  │  HTTP
python-service (FastAPI + MongoDB)   ── chunking, embeddings, retrieval, generation
```

---

## Table of contents

### Part I — Foundations

| # | Chapter | What you get |
|---|---|---|
| 1 | [Why keyword search fails](01-why-keyword-search-fails.md) | The problem, and the intuition behind the fix |
| 2 | [Setting up](02-setting-up.md) | Python, virtual environments, and the traps in them |
| 3 | [What RAG actually is](03-what-rag-actually-is.md) | The two halves, and why people confuse them |

### Part II — The retrieval half

| # | Chapter | What you get |
|---|---|---|
| 4 | [Chunking](04-chunking.md) | Splitting text, overlap, and measuring the right size |
| 5 | [Embeddings](05-embeddings.md) | What a vector is, why unit length matters |
| 6 | [Retrieval](06-retrieval.md) | Cosine similarity in one line of NumPy |
| 7 | [Testing retrieval](07-testing-retrieval.md) | Testing something with no single right answer |

### Part III — The generation half

| # | Chapter | What you get |
|---|---|---|
| 8 | [Grounding](08-grounding.md) | Prompting a model to answer only from what you give it |
| 9 | [Providers](09-providers.md) | Gemini, OpenAI, Ollama behind one function |
| 10 | [The first HTTP service](10-fastapi-service.md) | FastAPI, request models, error codes |

### Part IV — Storage

| # | Chapter | What you get |
|---|---|---|
| 11 | [Two databases, one system](11-two-databases.md) | Why PostgreSQL *and* MongoDB, honestly |
| 12 | [The consistency problem](12-consistency.md) | What happens when one write succeeds and one fails |

### Part V — The full stack

| # | Chapter | What you get |
|---|---|---|
| 13 | [The Node API](13-node-api.md) | Express, TypeScript, and joining across two stores |
| 14 | [The front end](14-frontend.md) | React without a framework, state without a library |
| 15 | [Designing for trust](15-designing-for-trust.md) | Why the sources are always visible |
| 16 | [Accessibility](16-accessibility.md) | Contrast, measured — and three failures we found |

### Part VI — Reliability

| # | Chapter | What you get |
|---|---|---|
| 17 | [Falling back](17-fallback.md) | Which failures are worth retrying elsewhere |
| 18 | [Rate limiting](18-rate-limiting.md) | Protecting a quota you cannot afford to lose |
| 19 | [Measuring it](19-measuring.md) | The benchmark, and what it decided |

### Part VII — Containers

| # | Chapter | What you get |
|---|---|---|
| 20 | [Docker](20-docker.md) | Three images, and why one is 8.88 GB |
| 21 | [Compose](21-compose.md) | Dev and production from one file |
| 22 | [The nginx caching bug](22-nginx-dns.md) | A 502 that only appears on redeploy |

### Part VIII — Kubernetes

| # | Chapter | What you get |
|---|---|---|
| 23 | [Manifests](23-kubernetes.md) | Deployments, Services, probes, Secrets |
| 24 | [Three portability bugs](24-portability.md) | What only breaks once you leave Compose |

### Part IX — Shipping

| # | Chapter | What you get |
|---|---|---|
| 25 | [Continuous integration](25-ci.md) | Tests that cost nothing to run |
| 26 | [Deploying to AWS](26-aws.md) | Lightsail, start to finish |
| 27 | [Paying for it](27-cost.md) | Credits, quotas, and turning it off |

### Appendices

| # | Appendix | What you get |
|---|---|---|
| A | [Every bug, in order](A-bugs.md) | The full list, with error messages |
| B | [Command reference](B-commands.md) | Everything you will need to type |
| C | [Glossary](C-glossary.md) | Plain-English definitions |

---

## How to read this

Straight through, if you are building along. The chapters follow the order the
project was actually built, and each one leaves you with something that runs.

If you are here for one thing — the nginx bug, the fallback logic, the cost
model — the table of contents is a fair index and the chapters stand alone.

## Every output here was produced by running it

No output in this book is illustrative. Every number, every error message and
every block of terminal output was copied from an actual run.

That rule caught a mistake while writing Chapter 5: a worked example had
plausible-looking scores that turned out to be wrong when the code was actually
run — and the real numbers contained a surprise the invented ones had smoothed
over. The chapter is better for it. If you run the commands and get something
different, trust your terminal.

## Conventions

Commands you type look like this:

```bash
python -m venv venv
```

Output you should see looks like this:

```
36 passed in 5.04s
```

When something goes wrong, it appears in a box like this:

> **What went wrong**
>
> The real error message, followed by why it happened and what fixed it.

## The code

Everything in this book is in the repository this book lives in. Each chapter
names the files it touches, so you can read the finished version alongside the
explanation.

---

*Written alongside the build, in August 2026.*
