# Chapter 14 — The front end

**Files:** `web/src/App.tsx`, `api.ts`, `components/*.tsx`

## What it has to do

Four things:

1. Take a question and show an answer
2. Show the passages the answer came from
3. Let you add and remove notes
4. Let you choose which model answers

That is the whole surface. Worth writing down, because the default instinct when
starting a front end is to reach for tooling sized for something much larger.

## What it is built with

```json
"dependencies": {
  "react": "^18.3.1",
  "react-dom": "^18.3.1"
}
```

Two runtime dependencies. No Redux, no React Query, no Tailwind, no component
library, no router.

Not out of minimalism for its own sake. Each of those solves a problem this app
does not have:

| Tool | Solves | Do we have it? |
|---|---|---|
| Redux / Zustand | State shared across many distant components | No — one screen |
| React Query | Caching, refetching, invalidation across views | No — three calls |
| Tailwind | Consistency across a large team and codebase | No — one person, 400 lines of CSS |
| A router | Multiple pages | No — one page |
| A component library | Buttons and inputs at scale | No — six elements |

Adding any of them means learning its conventions, tracking its updates, and
explaining it later. For a project this size that is cost without return.

> Say this precisely in an interview. Not *"frameworks are bloat"* — that is a
> slogan. Say *"one screen, three API calls, no shared state between distant
> components, so a state library would have been machinery without a job."*
> The first is an attitude; the second is a decision.

## State, in eight `useState` calls

```typescript
const [documents, setDocuments] = useState<DocumentRow[]>([]);
const [providers, setProviders] = useState<Provider[]>([]);
const [provider, setProvider] = useState<string | null>(null);
const [loaded, setLoaded] = useState(false);
const [notesOpen, setNotesOpen] = useState(false);
const [query, setQuery] = useState("");
const [mode, setMode] = useState<Mode>("ask");
const [result, setResult] = useState<Result | null>(null);
const [busy, setBusy] = useState(false);
const [error, setError] = useState<string | null>(null);
```

All of it lives in `App`, and children receive what they need as props. That is
the simplest thing that works, and at this size it stays readable.

It would stop being readable at maybe twice this. The signal to reach for
something else is not a line count — it is when you start passing a prop through
a component that does not use it, purely to reach a grandchild. That has not
happened here.

## One place that talks to the server

```typescript
async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: init?.body ? { "content-type": "application/json" } : undefined,
  });

  if (!response.ok) {
    // The API reports problems as { error, detail? }; fall back to the status
    // line when the body is not JSON at all.
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? body?.error ?? `request failed (${response.status})`);
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}
```

Every request goes through here, so error handling is written once.

Three details that each came from something going wrong somewhere:

**`fetch` does not throw on 4xx or 5xx.** This surprises people coming from other
HTTP clients. A 500 response is a *successful* fetch with `ok === false`. Without
the explicit check, an error response is parsed as if it were data and fails
somewhere confusing later.

**`.catch(() => null)` on the body.** An error body is not always JSON — nginx
returns HTML for a 502. Without the catch, the error handler throws while
handling an error, and the original problem is lost.

**The 204 case.** `DELETE` returns 204 No Content. Calling `.json()` on an empty
body throws. One conditional avoids it.

That chain — `body?.detail ?? body?.error ?? "request failed (…)"` — is the last
link in the story from Chapters 10 and 13. The Python service produced a good
message, the Node service passed it through, and here it finally reaches a human:

```
429 RESOURCE_EXHAUSTED. You exceeded your current quota...
```

Three services, and the sentence survived.

## Every request has three states

```typescript
async function run(event: React.FormEvent) {
  event.preventDefault();
  if (!query.trim() || busy) return;

  setBusy(true);
  setError(null);
  try {
    setResult(
      mode === "ask"
        ? await api.ask(query.trim(), provider ?? undefined)
        : await api.search(query.trim()),
    );
  } catch (cause) {
    setResult(null);
    setError(cause instanceof Error ? cause.message : "request failed");
  } finally {
    setBusy(false);
    // The input is disabled while waiting, which drops focus; put it back so
    // the next question can be typed straight away.
    inputRef.current?.focus();
  }
}
```

**`if (busy) return`** stops a double submit. Generation takes several seconds;
without this, an impatient second click sends a second request.

**`setResult(null)` in the catch.** Without it, a failed request leaves the
previous answer on screen next to an error message. The reader cannot tell
whether that answer is stale or current.

**The `finally` block.** `busy` is cleared whether the request succeeded or
failed — otherwise one error leaves the form permanently disabled.

**Restoring focus.** The input is disabled while waiting, and a disabled element
loses focus. Without this line, you type a question, get an answer, and have to
click the box again before typing the next one. A one-line fix for a small
constant annoyance.

## Three small bugs

None of these crashed anything. All three were found by reading the code and
asking what happens in the less common case.

> **Bug 1: shadowing a global**
>
> ```typescript
> {documents.map((document) => (
>   <li key={document.id}>{document.title}</li>
> ))}
> ```
>
> Reads perfectly. `document` is also the browser's global DOM object, and inside
> this callback it now refers to a database row.
>
> Nothing breaks — no DOM access happens in there. But the next person to add
> `document.querySelector` inside this block gets a confusing runtime error, and
> the compiler will not help, because a `DocumentRow` is a perfectly valid thing
> to have.
>
> Renamed to `doc`.

> **Bug 2: a wrong state that flashes**
>
> ```typescript
> {documents.length === 0 ? <p>Nothing added yet.</p> : <ul>...</ul>}
> ```
>
> `documents` starts as `[]`, so on every page load the panel says *"Nothing
> added yet"* until the fetch returns — even when there are documents.
>
> The bug is asserting something before you know it. Added a `loaded` flag:
>
> ```typescript
> {!loaded ? <p>Loading…</p>
>          : documents.length === 0 ? <p>Nothing added yet.</p>
>          : <ul>...</ul>}
> ```
>
> Three states, not two: *unknown*, *empty*, *has items*.

> **Bug 3: a button that would submit**
>
> ```typescript
> <button className="notes-toggle" onClick={...}>Notes</button>
> ```
>
> A `<button>` without `type` defaults to `type="submit"`. This one sits outside
> any form, so today it does nothing.
>
> Found by listing every button and its resolved type:
>
> ```javascript
> [...document.querySelectorAll('button')].map(b => ({ text: b.textContent, type: b.type }))
> // → { text: "Notes", type: "submit", inForm: false }
> ```
>
> Harmless now; a latent bug the moment anyone wraps this area in a form. Fixed
> with `type="button"`.

The pattern across all three: **the code was correct for the case in front of
you, and wrong for a case that had not happened yet.**

## Typed responses

```typescript
export interface AskResult {
  kind: "ask";
  question: string;
  answer: string;
  provider: string;
  model: string;
  /** Non-empty when an earlier provider refused and this one stood in. */
  fallbacks: Attempt[];
  hits: Hit[];
}

export type Result = SearchResult | AskResult;
```

`kind` makes this a discriminated union. Check it once and TypeScript knows which
fields exist:

```typescript
{result.kind === "ask" && (
  <>
    <p className="answer">{result.answer}</p>
  </>
)}
```

Outside that branch, `result.answer` is a compile error — a `SearchResult` has no
answer. The two result shapes cannot be confused, and the compiler enforces it
rather than a convention.

## Why Vite

```typescript
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Dev requests to /api go to the Node service, so the browser only ever
    // talks to one origin and CORS never comes up during development.
    proxy: {
      "/api": { target: "http://localhost:3011", changeOrigin: true },
    },
  },
});
```

The proxy is the useful part. The dev server runs on 5173 and the API on 3011 —
different origins, so the browser would normally block the request.

Rather than configure CORS for development, the dev server forwards `/api` to the
API. The browser sees one origin. In production nginx does exactly the same
thing, so **development and production behave identically** and there is no
CORS-only-in-dev class of bug.

```
dev:         browser → :5173 → proxy → :3011
production:  browser → nginx → :3001
```

Same shape, and the front end never learns the API's address. It always calls
`/api`.

## The build

```bash
npm run build
```

```
✓ 35 modules transformed.
dist/index.html                   0.40 kB │ gzip:  0.28 kB
dist/assets/index-6IPFrXNQ.css    7.97 kB │ gzip:  2.27 kB
dist/assets/index-FqY9TD2X.js   151.45 kB │ gzip: 48.77 kB
✓ built in 233ms
```

48 KB gzipped, and most of that is React itself. The CSS is 2.27 KB — the whole
design in Chapter 15, hand-written.

The build script is `tsc --noEmit && vite build`: typecheck first, then bundle.
A type error fails the build rather than shipping.

---

## What you should take from this chapter

| | |
|---|---|
| Two dependencies | React and React DOM — each addition needs a job |
| State in one place | Ten `useState` calls; the signal to change is prop drilling |
| One `call()` | `fetch` does not throw on 4xx; handle it once |
| Three states, not two | Unknown, empty, populated |
| The proxy | Dev and production behave the same, so no CORS-only bugs |

---

**Next:** [Chapter 15 — Designing for trust](15-designing-for-trust.md), where
the interface has to make an answer checkable.
