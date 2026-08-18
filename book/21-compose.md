# Chapter 21 — Compose

**Files:** `docker-compose.yaml`, `docker-compose.override.yaml`

## Five containers, one command

```bash
docker compose up -d --build
```

```
✓ Container semantic-rag-search-mongo-1           Healthy
✓ Container semantic-rag-search-postgres-1        Healthy
✓ Container semantic-rag-search-python-service-1  Started
✓ Container semantic-rag-search-node-api-1        Started
✓ Container semantic-rag-search-web-1             Started
```

Three services we built, two databases, one network, two volumes. Compose is
worth its keep the moment there is more than one container, and here there are
five.

## Starting in the right order

The Node service needs PostgreSQL. The Python service needs MongoDB. Starting all
five at once means two of them try to connect to databases that are still
initialising.

```yaml
  postgres:
    image: postgres:16-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U rag"]
      interval: 5s
      timeout: 3s
      retries: 10

  node-api:
    depends_on:
      postgres:
        condition: service_healthy
      python-service:
        condition: service_started
```

Two different conditions, deliberately:

- **`service_healthy`** — wait until the health check passes. PostgreSQL prints
  "ready" and then restarts once during first-time initialisation, so "the
  container started" is not the same as "the database accepts connections"
- **`service_started`** — the container is running. Enough for the Python
  service, which the Node service only calls on demand

Getting this wrong produces the most annoying class of bug: it works on a warm
machine where images are cached and containers start fast, and fails on a cold
one.

## Surviving a restart

```yaml
  postgres:
    restart: unless-stopped
```

On all five services.

This was added for a specific reason that only appears in Chapter 27: the AWS
deployment is *deleted* when not in use and recreated from a snapshot. A fresh
boot must bring the whole stack back with nobody logging in to start it.

`unless-stopped` means: restart on failure, restart on boot, but stay down if a
human explicitly stopped it. That last clause is what makes it different from
`always` — `docker compose stop` should mean stop.

It also fixed something visible immediately. Running `docker compose restart`
restarts every container simultaneously and **does not respect `depends_on`
ordering**. The Node service came up before PostgreSQL was ready and crashed:

```
node-api-1  | Error: connect ECONNREFUSED
...
node-api-1  | node-api listening on :3001
```

Two restarts, then healthy. The crash is visible in the log, and the restart
policy handled it without anyone noticing.

That is the Kubernetes-idiomatic answer too, arriving early: **let it crash and
be restarted, rather than building retry logic into the application.**

## The publishing problem

During development you want to reach everything — psql into PostgreSQL, curl the
Python service directly, connect a Mongo client.

On a public server you want the opposite. Only the web container should be
reachable; a database open to the internet is a serious mistake.

The naive answer is to comment lines out before deploying. That is the kind of
manual step that gets forgotten exactly once.

## The override file

Compose loads `docker-compose.override.yaml` automatically if it exists. So the
base file is production-shaped:

```yaml
# Only the web container publishes a port. Everything else talks over the
# internal compose network, so on a public server nothing else is reachable.
#
# On the server: WEB_PORT=80 in .env, and start with
#   docker compose -f docker-compose.yaml up -d --build
# The -f skips the dev override.

services:
  postgres:
    restart: unless-stopped
    image: postgres:16-alpine
    # no ports

  web:
    ports:
      - "${WEB_PORT:-8080}:80"
```

And the override adds development conveniences:

```yaml
# Local development only.
#
# Compose loads this file automatically alongside docker-compose.yaml, so
# `docker compose up` locally publishes the database and service ports.
#
# The server never loads it, because the deploy command names the base file
# explicitly.

services:
  postgres:
    ports: ["5432:5432"]
  mongo:
    ports: ["27017:27017"]
  python-service:
    ports: ["8000:8000"]
  node-api:
    ports: ["3001:3001"]
```

Two commands, two behaviours:

| Command | Loads | Publishes |
|---|---|---|
| `docker compose up` | base **+ override** | everything |
| `docker compose -f docker-compose.yaml up` | base only | web only |

The `-f` is the whole mechanism. Naming a file explicitly disables automatic
override loading.

This is better than a comment saying "remember to remove these before
deploying", because the safe behaviour is what the deployment script already
does.

## One port, parameterised

```yaml
  web:
    ports:
      - "${WEB_PORT:-8080}:80"
```

`${WEB_PORT:-8080}` means "use `WEB_PORT` if set, otherwise 8080".

Locally, 8080 — binding to 80 on macOS needs privileges. On the server,
`WEB_PORT=80` in `.env`, because that is where a browser looks by default.

One variable rather than a second compose file for a port number.

> This detail caused a small deployment stumble. The server's `.env` was created
> without `WEB_PORT`, so the stack came up on 8080 while the firewall only
> allowed 80. The site was unreachable and nothing was broken.
>
> `deploy/setup.sh` now guarantees it:
>
> ```bash
> grep -q '^WEB_PORT=' .env || echo "WEB_PORT=80" >> .env
> ```
>
> **A default that is right for development is a trap in production unless
> something enforces the production value.**

## Data that outlives containers

```yaml
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  postgres-data:
  mongo-data:
```

Named volumes. Without them, `docker compose down` destroys the databases.

The distinction matters and is easy to get wrong at the worst moment:

| Command | Containers | Data |
|---|---|---|
| `docker compose stop` | Stopped | Kept |
| `docker compose down` | Removed | **Kept** — volumes survive |
| `docker compose down -v` | Removed | **Destroyed** |

Which is why `setup.sh` prints both, with comments:

```
docker compose -f docker-compose.yaml down          # stop, keep data
docker compose -f docker-compose.yaml down -v       # stop, wipe data
```

## Verifying persistence

Persistence is a claim, so it was tested:

```bash
# before
1 doc, 5 chunks

docker compose -f docker-compose.yaml restart

# after
1 doc, 5 chunks
mongo chunks: 5
```

Every container restarted, the data survived. With the in-memory store from
Chapter 11 it would not have — which is the whole reason MongoDB is in the
system.

## Secrets

```yaml
  python-service:
    environment:
      LLM_PROVIDER_CHAIN: ${LLM_PROVIDER_CHAIN:-gemini,openai}
      GEMINI_API_KEY: ${GEMINI_API_KEY:-}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
```

Compose reads `.env` automatically and substitutes. The keys are never in the
compose file, which is committed; they are in `.env`, which is not.

The `:-` defaults matter. Without them, a missing `GEMINI_API_KEY` makes Compose
warn on every command. With them it is an empty string, and Chapter 9's
`is_available` skips that provider cleanly.

## The internal network

Compose puts every service on one network, where **service names resolve as
hostnames**:

```yaml
      MONGO_URI: mongodb://mongo:27017
      DATABASE_URL: postgres://rag:rag@postgres:5432/rag
      RAG_SERVICE_URL: http://python-service:8000
```

`mongo`, `postgres`, `python-service` — the service names from the file. No IP
addresses anywhere.

This is convenient and it is also where the next chapter's bug lives. Those names
resolve through Docker's embedded DNS server, and one of the containers caches
the answer.

---

## What you should take from this chapter

| | |
|---|---|
| `depends_on` conditions | `service_healthy` for databases, `service_started` otherwise |
| `restart: unless-stopped` | Survives reboot; a human `stop` still means stop |
| Base file is production | The override adds development ports, automatically |
| `-f` disables the override | The deploy command is the safe one by default |
| `down` vs `down -v` | One keeps your data, one does not |
| Service names as hostnames | Convenient — and the subject of Chapter 22 |

---

**Next:** [Chapter 22 — The nginx caching bug](22-nginx-dns.md), a 502 that only
appears after a redeploy.
