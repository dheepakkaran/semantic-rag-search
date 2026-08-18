# Chapter 13 — The Node API

**Files:** `node-api/src/routes.ts`, `db.ts`, `ragClient.ts`, `app.ts`

## Why a second language

The Python service already speaks HTTP. Adding a Node service in front of it
needs justifying, or it is complexity for its own sake.

The reason is narrow and real: **Python owns the model, Node owns the web layer.**

Everything that needs the embedding model, NumPy, or a provider SDK lives in
Python — that ecosystem is where those libraries are. Everything else — the REST
surface the browser talks to, the relational data, request shaping — is ordinary
web work, and Node does it with less ceremony.

The split also produces a genuinely useful property: **the browser talks to
exactly one service.** The Python service is never exposed publicly. It has no
CORS configuration, no authentication surface, no rate limiting of its own. It
sits on an internal network and answers one client.

> The honest counter-argument, again: one FastAPI service could serve the front
> end and hold the metadata too. It would be one less container and one less
> language. The split is defensible, not mandatory — and "here is what it costs"
> is a better answer than pretending it was forced.

## What each service owns

```
browser
   │  /api/*
node-api ──── PostgreSQL      document metadata
   │  HTTP
python-service ──── MongoDB   chunks, vectors, the model, the provider calls
```

| | node-api | python-service |
|---|---|---|
| Language | TypeScript | Python |
| Owns | Document metadata | Chunks, vectors, generation |
| Database | PostgreSQL | MongoDB |
| Public? | Yes, via nginx | No |

## The one job that justifies PostgreSQL

Search comes back from the Python service like this:

```json
{ "document_id": "1", "text": "the family of tricks...", "score": 0.455 }
```

A `document_id`, and no title — because that service has never seen a title. It
was given `"1"` at ingest and that is all it knows.

The interface needs to show *"Lectures 3-5 — Training, Overfitting, Embeddings"*
under each citation. So the Node service fills it in:

```typescript
/** Attach each hit's document title in one query, not one query per hit. */
async function withTitles(hits: Hit[]): Promise<TitledHit[]> {
  const ids = [
    ...new Set(hits.map((hit) => Number(hit.document_id)).filter(Number.isInteger)),
  ];
  if (ids.length === 0) {
    return hits.map((hit) => ({ ...hit, title: null }));
  }

  const { rows } = await pool.query<{ id: number; title: string }>(
    "select id, title from documents where id = any($1::int[])",
    [ids],
  );
  const titles = new Map(rows.map((row) => [String(row.id), row.title]));

  return hits.map((hit) => ({ ...hit, title: titles.get(hit.document_id) ?? null }));
}
```

**This function is the reason PostgreSQL is in the system.** It is a join across
the two stores, done in application code because the stores cannot join to each
other.

Three details worth the space.

**`new Set`.** Four hits often come from the same document. Deduplicating means
one id in the query instead of four.

**`= any($1::int[])`.** One query for all ids. The naive version — a query per
hit — is the N+1 problem: four hits, four round trips. At `k=10` it is ten. The
test pins this down:

```typescript
// One lookup for all hits, not one per hit.
expect(query).toHaveBeenCalledTimes(1);
```

**`?? null`.** A document deleted between the search and the title lookup returns
no row. Rather than crash, the hit gets `title: null`, and the front end shows
`document 4`. Degraded, not broken.

## Talking to the Python service

One file knows the retrieval service exists:

```typescript
const BASE_URL = process.env.RAG_SERVICE_URL ?? "http://localhost:8000";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, init);
  } catch (cause) {
    // The service is down or unreachable — distinct from it rejecting us.
    throw new RagServiceError(503, `retrieval service unreachable at ${BASE_URL}`);
  }
  ...
}
```

The distinction in that comment is worth having. A `fetch` that throws means the
service could not be reached at all — wrong URL, container not up, DNS failure.
A response with a bad status means it was reached and said no. Those need
different debugging, and collapsing them into one message wastes the difference.

`RAG_SERVICE_URL` defaults to localhost so `npm run dev` works with nothing
configured, and Compose and Kubernetes override it. Same pattern as `MONGO_URI`
in Chapter 11: **sensible default, overridable.**

## The bug: an error inside an error

> **What went wrong**
>
> Chapter 10 fixed the quota error so the Python service returned a clean 429:
>
> ```json
> {"detail": "429 RESOURCE_EXHAUSTED... Please retry in 34s"}
> ```
>
> The browser showed this:
>
> ```json
> {"error":"retrieval service failed",
>  "detail":"{\"detail\":\"429 RESOURCE_EXHAUSTED. {'error': {'code': 429..."}
> ```
>
> A JSON document, stringified, inside another JSON document. The useful sentence
> was there — two levels down, escaped, unreadable.
>
> The cause was one line:
>
> ```typescript
> throw new RagServiceError(response.status, await response.text());
> ```
>
> `response.text()` takes the whole body as a string. That string is JSON. It
> then became the `detail` field of another JSON object.

The fix unwraps one level:

```typescript
if (!response.ok) {
  // FastAPI reports problems as { detail }. Unwrap it, so the browser gets
  // "quota exceeded, retry in 34s" rather than that sentence buried inside a
  // stringified JSON body inside another JSON body.
  const body = await response.text();
  let message = body;
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    if (typeof parsed.detail === "string") message = parsed.detail;
  } catch {
    // Not JSON — keep the raw text, which is still better than nothing.
  }
  throw new RagServiceError(response.status, message);
}
```

The `catch` matters. Not every error body is JSON — nginx returns HTML for a 502,
for instance. Falling back to the raw text keeps something useful instead of
throwing while handling an error.

### This is Chapter 10's lesson again

Chapter 10: *an error that crosses a boundary should keep its meaning*. A 429
became a 500.

Here: the status survived, but the *message* got wrapped in a layer of packaging.

Same failure, one level up. Each service was doing something locally reasonable —
"attach the upstream body to my error" — and the composition destroyed
readability.

> **Every boundary an error crosses is a chance to lose information. Two
> boundaries, two chances.**

## One error handler

```typescript
app.use(
  (error: unknown, _request: Request, response: Response, _next: NextFunction) => {
    if (error instanceof RagServiceError) {
      return response
        .status(error.status)
        .json({ error: "retrieval service failed", detail: error.message });
    }

    console.error(error);
    response.status(500).json({ error: "internal error" });
  },
);
```

Every route ends with `catch (error) { next(error); }` and nothing else. Handlers
do not format error responses; one place does.

The two branches carry a real distinction:

- **`RagServiceError`** — something upstream said no. Pass its status through
- **Anything else** — our bug. Log it, return 500

That is the correct use of 500: *this service has a bug*. Chapter 10's mistake
was using it for someone else's quota.

## Why TypeScript

```typescript
export interface DocumentRow {
  id: number;
  title: string;
  chunk_count: number;
  created_at: string;
}

const { rows } = await pool.query<DocumentRow>("select * from documents");
```

`rows` is now `DocumentRow[]`. Misspell `row.titel` and the compiler says so
before the code runs.

This matters most at boundaries. The shapes crossing this service — a database
row, a Python service response, a browser request — are the places where a typo
becomes `undefined` at runtime and a confusing bug an hour later.

```bash
npm run typecheck
```

```
> tsc --noEmit
```

No output means no errors. It runs in CI on every push.

## Tests with everything mocked

```typescript
vi.mock("../src/db.js", () => ({
  pool: { query: (...args: unknown[]) => query(...args) },
  initSchema: vi.fn(),
}));

vi.mock("../src/ragClient.js", async () => { ... });
```

Both dependencies replaced. The tests need no PostgreSQL and no Python service,
so they run in about 300 milliseconds with nothing installed.

What is left to test is exactly this service's own logic: input validation, the
titles join, the compensating delete, status pass-through. Everything else
belongs to the thing being mocked.

```
Test Files  1 passed (1)
     Tests  15 passed (15)
  Duration  307ms
```

## Schema without migrations

```typescript
export async function initSchema(): Promise<void> {
  await pool.query(`
    create table if not exists documents (
      id          serial primary key,
      title       text        not null,
      chunk_count integer     not null default 0,
      created_at  timestamptz not null default now()
    )
  `);
}
```

Run at startup. `if not exists` makes it idempotent.

No migration tool. The comment says why, and where that stops being true:

```typescript
/**
 * Created on startup rather than through a migration tool. One table with no
 * history does not need migrations; if a second table arrives, it will.
 */
```

One table, created once, never altered. A migration tool would be more machinery
than schema. **Naming the condition under which you would add it** is what makes
this a decision rather than an omission.

---

## What you should take from this chapter

| | |
|---|---|
| Why two languages | Python owns the model; Node owns the web layer |
| The join | Attaching titles is why PostgreSQL is in the system |
| Avoid N+1 | One query with `= any($1::int[])`, asserted in a test |
| The bug | An error body stringified inside another error body |
| One error handler | Routes call `next(error)`; one place formats |
| 500 means | *This* service has a bug — not someone else's quota |

---

**Next:** [Chapter 14 — The front end](14-frontend.md), where React arrives
without a framework and state arrives without a library.
