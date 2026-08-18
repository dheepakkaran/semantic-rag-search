# Chapter 9 — Providers

**File:** `python-service/rag/llm.py`

## One function, several models

Retrieval does not care which model writes the answer. It hands over a prompt and
receives text. That is the entire contract.

So generation sits behind one function:

```python
def generate(prompt: str, provider: str | None = None) -> Generation:
    ...
```

And which model runs is an environment variable:

```
LLM_PROVIDER_CHAIN=gemini,openai
```

This looks like over-engineering for a project with one user. It is not, and this
chapter is about the three concrete things it buys.

## Why bother

**1. The free tier is 20 requests a day.**

Not 20 per minute. Twenty per day.

```
429 RESOURCE_EXHAUSTED. Quota exceeded for metric:
generativelanguage.googleapis.com/generate_content_free_tier_requests,
limit: 20, model: gemini-3.6-flash
```

That limit was hit within an afternoon of ordinary testing. A system with one
hardcoded provider is simply down for the rest of the day. Chapter 17 turns this
into automatic fallback.

**2. Demos happen where the network does not.**

`LLM_PROVIDER=ollama` runs a small model on the local machine. No key, no
network. If an interview room has no internet, the demo still works.

**3. Tests must not cost money.**

`LLM_PROVIDER=mock` returns a fixed string. The whole pipeline runs — chunking,
embedding, retrieval, prompt assembly — with no API call. That is what makes the
test suite free to run on every push.

Any one of those justifies the abstraction. Together they make it obvious.

## The shape

```python
DEFAULT_MODELS = {
    "gemini": "gemini-3.6-flash",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.2:3b",
    "mock":   "mock",
}

KEY_FOR = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}


def model_for(provider: str) -> str:
    return os.getenv(f"{provider.upper()}_MODEL", DEFAULT_MODELS.get(provider, provider))
```

Each provider has a default model, overridable by environment variable. That
override matters more than it looks — see the bug below.

`KEY_FOR` maps providers to the key they need. Ollama and mock are absent because
they need none, which is exactly what `is_available` uses:

```python
def is_available(provider: str) -> bool:
    key = KEY_FOR.get(provider)
    return True if key is None else bool(os.getenv(key))
```

Note what this does *not* claim. It says a key is present. It says nothing about
whether that key has quota left, or whether the Ollama daemon is running. Those
are only discoverable by making a request, and the docstring says so:

```python
"""Whether this provider could be called at all.

Only key presence is checked. Ollama needs a local daemon and Gemini needs
quota left, and neither can be known without making a request.
"""
```

Being precise about what a function does not guarantee is worth as much as being
precise about what it does.

## Calling a provider

```python
def _call(prompt: str, provider: str) -> str:
    if provider == "gemini":
        from google import genai
        from google.genai import errors

        client = genai.Client(api_key=_require_key("GEMINI_API_KEY"))
        try:
            response = client.models.generate_content(
                model=model_for("gemini"), contents=prompt
            )
        except errors.APIError as exc:
            raise LLMError(exc.code or 502, _clean(str(exc)), provider) from exc
        return response.text or ""
    ...
```

Three deliberate choices.

**Imports are inside the function.** `import openai` only runs if someone
actually selects OpenAI. So a deployment using only Gemini does not need the
OpenAI package installed, and a missing optional dependency fails at the moment
you ask for it, with a clear message, rather than at startup.

**Every provider error becomes `LLMError`.** Each SDK raises its own exception
type. Converting them at the boundary means the rest of the system deals with one
error type carrying one status code, and nothing above this file imports a
provider SDK.

**Errors are trimmed.** Both SDKs stringify the entire JSON error body — several
hundred characters of nested detail:

```python
def _clean(message: str) -> str:
    """Trim a provider's error to its first line."""
    return message.strip().splitlines()[0][:300]
```

The first line carries the part a caller can act on. The rest is noise in a log.

## The bug that justified `model_for`

> **What went wrong**
>
> The default model was `gemini-2.5-flash`, written from memory while building.
> The first real call returned:
>
> ```
> 404 NOT_FOUND. This model models/gemini-2.5-flash is no longer available
> to new users. Please update your code to use models/gemini-3.6-flash for
> the latest features and improvements.
> ```
>
> The model had been retired. Nothing in the code was wrong — the world had
> moved.
>
> The fix was one word in one dictionary. But notice what made it a one-word fix:
> the model name was in a single named place, and overridable by environment
> variable. Had it been inlined at the call site, it would have been a code
> change and a redeploy; with `GEMINI_MODEL` it can be changed on a running
> server without touching the image.

There is a wider lesson, and it applies to writing as much as to code.

**Model names, API shapes and free-tier limits change faster than your code
does.** Anything you "know" about a provider has a shelf life. Put such facts in
one place, make them overridable, and verify them by making a real call rather
than by trusting memory — including your own.

## The error type

```python
class LLMError(RuntimeError):
    """A provider refused the request.

    Carries the provider's own status code so the API can pass it through
    rather than reporting every upstream problem as a 500.
    """

    def __init__(self, status: int, message: str, provider: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.provider = provider

    @property
    def retryable(self) -> bool:
        return self.status in RETRYABLE
```

The status code is the whole point. Chapter 10 shows what happens without it, and
Chapter 17 uses `retryable` to decide whether trying another provider is worth
the wait.

## Which statuses are worth retrying

```python
RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504}
```

The comment beside it explains the shape of the set:

```python
# Statuses worth trying the next provider for: quota, overload, transient
# server faults. A 401 or a 400 is not in here — a bad key or a malformed
# request will fail the same way everywhere, so moving on just wastes time.
```

This distinction is the substance of Chapter 17. A quota error is about *this
provider right now*; another provider will succeed. A bad request is about the
request; every provider will reject it identically, so trying three of them turns
one fast failure into a slow one.

## The mock provider

```python
if provider == "mock":
    return "[mock] no model was called"
```

Two lines, and they carry the test suite.

With `LLM_PROVIDER=mock` the full pipeline runs end to end with no key, no
network and no cost. That is what allows this in CI:

```yaml
- run: pytest -q
```

with no secrets configured at all.

There is a second use. During development you can exercise the whole system —
ingest, search, ask, the front end — without spending any of a twenty-request
daily budget on requests where you are testing the plumbing rather than the
answer.

## Configuring it

```
LLM_PROVIDER_CHAIN=gemini,openai   try each in turn, fall back on refusal
LLM_PROVIDER=gemini                a single provider, no fallback
```

Two variables, and the second exists for compatibility:

```python
def chain() -> list[str]:
    raw = os.getenv("LLM_PROVIDER_CHAIN")
    if raw:
        names = [name.strip() for name in raw.split(",") if name.strip()]
    else:
        names = [os.getenv("LLM_PROVIDER", "gemini")]
    ...
```

`LLM_PROVIDER` was the original setting, before fallback existed. Keeping it
meaning "this one, no fallback" means nothing that already set it changed
behaviour when the feature landed.

## Failing loudly on a typo

```python
unknown = [name for name in names if name not in DEFAULT_MODELS]
if unknown:
    raise ValueError(
        f"unknown provider(s) {unknown}; expected any of {sorted(DEFAULT_MODELS)}"
    )
```

Set `LLM_PROVIDER_CHAIN=gemini,openai2` and the service refuses to start with a
message naming the mistake and listing the valid options.

The alternative — silently skipping the unknown name — produces a system that
appears to work while quietly not using the provider you configured. Fail fast,
and say what you expected.

---

## What you should take from this chapter

| | |
|---|---|
| Why swappable | 20 requests/day, offline demos, free tests |
| Imports inside functions | Optional dependencies stay optional |
| One error type | Nothing above this file imports a provider SDK |
| Model names in one place | They get retired; make it a one-word fix |
| Retryable vs not | A quota error moves on; a bad key does not |

---

**Next:** [Chapter 10 — The first HTTP service](10-fastapi-service.md), where
functions become an API and a status code turns out to matter.
