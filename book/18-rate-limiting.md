# Chapter 18 — Rate limiting

**File:** `web/nginx.conf`

## The problem the internet creates

Locally, `/ask` is free to abuse. You are the only user.

The moment it has a public IP, that changes. Anyone who finds the URL can hold
down Enter, and each request spends part of a quota that is **twenty per day**.

There is no billing risk on a free tier — you cannot be charged for what you do
not have. The risk is subtler: **the demo stops working, and you find out during
the demo.**

## Which endpoint needs protecting

Not all of them.

| Endpoint | Costs | Protect? |
|---|---|---|
| `GET /api/search` | CPU, ~4 ms | No |
| `GET /api/documents` | One SQL query | No |
| `POST /api/documents` | CPU, embedding | Not really |
| **`POST /api/ask`** | **A quota'd API call** | **Yes** |

One endpoint spends a resource you cannot replace before midnight. Rate limiting
everything would be simpler to write and would slow down the parts that cost
nothing.

## Where to put it

Three plausible places:

| | |
|---|---|
| **Python service** | Closest to the cost. But it is behind two other services, so a blocked request has already travelled the whole stack |
| **Node service** | Reasonable. Needs a dependency and some state |
| **nginx** | Already in front of everything. Config only, no dependency, no code |

nginx wins on a simple argument: **it is already there.** It serves the static
files and proxies the API. Adding a limit is four lines of configuration, and a
blocked request is rejected before it reaches any application code at all.

## The configuration

```nginx
# Rate limit for the one endpoint that costs money.
#
# /api/ask calls a hosted language model on every request, so an open instance
# on the public internet is someone else's free API quota. Retrieval and the
# document endpoints are cheap and local, so they are left alone.
#
# 6 requests per minute per IP, with a burst of 3 so a quick second question
# is not punished. This lives here rather than in the Node service because
# nginx already sits in front of everything and it needs no new dependency.
limit_req_zone $binary_remote_addr zone=ask_limit:10m rate=6r/m;

server {
    listen 80;

    location = /api/ask {
        limit_req zone=ask_limit burst=3 nodelay;
        limit_req_status 429;

        proxy_pass $node_api/api/ask;
        ...
    }
}
```

Four directives, each doing something specific.

### `limit_req_zone $binary_remote_addr zone=ask_limit:10m rate=6r/m`

Defines the limit.

- **`$binary_remote_addr`** — the key. The client IP, in binary form, which is
  4 bytes for IPv4 rather than the ~15 of the text form. At scale that matters;
  here it is simply the conventional choice.
- **`zone=ask_limit:10m`** — a 10 MB shared memory region holding the counters.
  Roughly 160,000 IPv4 addresses, which is generous.
- **`rate=6r/m`** — six requests per minute per IP. One every ten seconds.

This directive must sit in the `http` context, not inside `server`. Because the
file is dropped into `conf.d/`, which nginx includes inside `http`, putting it at
the top of the file works.

### `limit_req zone=ask_limit burst=3 nodelay`

Applies it.

`burst=3` allows three requests to queue beyond the steady rate. Without a
burst, six per minute means *exactly* one every ten seconds, and asking two
questions back to back gets the second rejected — which is normal human
behaviour, not abuse.

`nodelay` says: serve the burst immediately rather than spacing them out. Without
it nginx would hold the second request for ten seconds and then answer, which
feels like the app has hung.

Together: **a small burst is served instantly, sustained hammering is refused.**

### `limit_req_status 429`

nginx returns `503 Service Unavailable` by default. That is wrong here — the
service is fine, the client is going too fast. `429 Too Many Requests` says
exactly that.

Same principle as Chapter 10: **the status code should mean what happened.**

### `location = /api/ask`

The `=` makes this an exact match, so it applies to `/api/ask` and nothing else.
Everything else falls through to the general `location /api/` block with no limit.

## Testing it

Not by reading the config — by hitting it:

```bash
for i in $(seq 1 10); do
  printf "%s " "$(curl -s -o /dev/null -w '%{http_code}' \
    -X POST localhost:8080/api/ask \
    -H 'content-type: application/json' -d '{"question":"test"}')"
done
```

```
200 200 200 200 429 429 429 429 429 429
```

Four succeeded, six refused.

Four, not three, and the arithmetic is worth following: the burst allows 3
queued, plus 1 at the steady rate that was available immediately. Then the bucket
is empty and everything else is refused until it refills at six per minute.

That is the configuration behaving exactly as written — and the only way to know
that is to run it.

## What it does not protect against

Honest limits, because a rate limit invites overconfidence.

**One IP, one limit.** Anyone with several addresses gets several allowances.
Defending against that needs authentication, and this app has no accounts.

**It is per instance — and this one is not hypothetical.**

The counters live in that 10 MB shared memory zone, and "shared" means shared
*within one nginx process*. Two nginx containers keep two independent counters.

This was discovered by running the same test against both deployments:

```bash
# Docker Compose — one web container
200 200 200 429 429 429 429
```

```bash
# Kubernetes — two web replicas
200 200 200 200 200 200 200 200
```

Same image, same configuration, same eight requests. On Compose the limit fired
after four. On Kubernetes it never fired at all.

The manifest is the reason:

```yaml
kind: Deployment
metadata:
  name: web
spec:
  replicas: 2
```

Two pods. The Service load-balances between them, so each nginx saw roughly four
requests — exactly the burst allowance. Neither pod ever had reason to refuse.

The effective limit is `6r/m × replicas`. Scale to ten pods and it is sixty a
minute, silently.

**This is the failure mode worth internalising: a per-instance limit gets weaker
as you scale, and nothing warns you.** The config is unchanged, the tests pass,
the deployment is healthy — and the protection quietly stopped working when a
replica count went from 1 to 2.

The fix is a shared counter. nginx can use Redis through a module; the more usual
answer in Kubernetes is to rate limit at the ingress, where there is one
enforcement point in front of all replicas. Neither is in this project, because
the AWS deployment in Chapter 26 runs one instance under Compose — where, as the
test above shows, the limit does work.

That is a real constraint on the design, not a rounding error, and it belongs in
the honest-limits list rather than in a footnote.

**Ingest is unprotected.** `POST /api/documents` runs the embedding model, which
costs CPU. A determined visitor could keep the box busy. It is not rate limited
because it does not spend the quota, and CPU recovers on its own.

For a demo behind an IP that is shared with nobody and deleted when not in use,
these are acceptable. On a real service with real users, none of them would be.

## The alternative that was not chosen

In Express it would look like this:

```typescript
import rateLimit from "express-rate-limit";
routes.post("/ask", rateLimit({ windowMs: 60_000, max: 6 }), askHandler);
```

Also fine. It was not chosen for two reasons:

**A new dependency for four lines of config.** `express-rate-limit` is a good
library; it is still one more package to install, update and understand.

**Rejected requests would travel further.** In nginx a blocked request never
reaches Node. In Express it has already been parsed and routed before being
turned away — cheap, but not free, and pointless work at the exact moment you are
trying to shed load.

There is a case for the Express version: it can rate limit per authenticated
user rather than per IP. The day this app has accounts, that becomes the better
answer.

## The general shape

This chapter is small, and the reasoning generalises further than the code:

> **Protect the thing that cannot be replaced, at the outermost layer that can
> see it, and return a status code that says what happened.**

- *The thing that cannot be replaced* — the daily quota, not CPU
- *The outermost layer* — nginx, not the service three hops in
- *A status that says what happened* — 429, not 503

---

## What you should take from this chapter

| | |
|---|---|
| Protect what is scarce | One endpoint spends a quota; the rest cost CPU |
| Put it at the edge | nginx is already there; no dependency, no code |
| Allow a burst | Two quick questions is human, not abuse |
| `nodelay` | Or the app appears to hang |
| Say 429, not 503 | The service is fine; the client is fast |
| Test by hitting it | `200 200 200 200 429 429 …` |

---

**Next:** [Chapter 19 — Measuring it](19-measuring.md), where a benchmark decides
an architectural question.
