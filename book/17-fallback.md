# Chapter 17 — Falling back

**Files:** `python-service/rag/llm.py`, `tests/test_fallback.py`

## The problem, precisely

The Gemini free tier allows **20 generations per day**.

Not per minute. Per day. An afternoon of ordinary development uses it up, and the
system is then down until midnight UTC.

But look at what is actually broken when that happens. Retrieval still works.
The right passages were found. The prompt was assembled. The only thing missing
is a model willing to turn those passages into a sentence.

That is a very recoverable failure — **if** generation is not welded to one
provider. Chapter 9 made sure it is not.

## The idea

Try providers in order. If one refuses, hand the *same prompt* to the next.

```
LLM_PROVIDER_CHAIN=gemini,openai
```

```
question
   ↓
retrieval  ────────────────────►  4 passages          (happens once)
   ↓
prompt     ────────────────────►  assembled           (happens once)
   ↓
gemini  ──► 429 quota exceeded
   ↓
openai  ──► answer ✓
```

Nothing is re-retrieved. Nothing is re-embedded. The fallback answer is grounded
in exactly the same passages, which is what makes it a fair substitute rather
than a different answer to a different question.

## The core

```python
def generate(prompt: str, provider: str | None = None) -> Generation:
    order = [provider] if provider else chain()

    attempts: list[Attempt] = []
    for name in order:
        model = model_for(name)

        if not is_available(name):
            attempts.append(Attempt(name, model, 503, f"{KEY_FOR[name]} is not set"))
            continue

        try:
            return Generation(_call(prompt, name), name, model, attempts)
        except LLMError as error:
            attempts.append(Attempt(name, model, error.status, str(error)))
            # A non-retryable refusal will repeat everywhere, so stop.
            if not error.retryable:
                break

    raise _exhausted(attempts)
```

Walk the chain. Skip providers with no key without calling them. On a retryable
refusal, record it and continue. On anything else, stop.

## The decision that matters

Not *how* to fall back — that is a loop. **Which failures are worth falling back
from.**

```python
# Statuses worth trying the next provider for: quota, overload, transient
# server faults. A 401 or a 400 is not in here — a bad key or a malformed
# request will fail the same way everywhere, so moving on just wastes time.
RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504}
```

| Status | Meaning | Try elsewhere? |
|---|---|---|
| **429** | Out of quota | ✅ Another provider has its own quota |
| **503** | Overloaded | ✅ Transient, and provider-specific |
| **500, 502, 504** | Server fault | ✅ Theirs, not yours |
| **401** | Bad key | ❌ Wrong keys everywhere; three failures instead of one |
| **400** | Malformed request | ❌ The request is wrong; every provider will say so |

The distinction is one question: **is this failure about the provider, or about
the request?**

Provider problems move. Request problems travel with you.

Getting it wrong is not neutral. Falling back on a 401 turns one fast failure
into three slow ones and then reports the *last* provider's error — so the user
sees "OpenAI: invalid key" when the real problem was the Gemini key they just
mistyped.

## Proving it in production, by accident

This was verified without meaning to. During deployment, an invalid Gemini key
was set as a test:

```
{"error":"retrieval service failed",
 "detail":"400 INVALID_ARGUMENT. API key not valid. Please pass a valid API key."}
HTTP 400
```

A `400`, not retryable, so the chain stopped at the first provider and reported
its error directly. Exactly as designed.

Then the key was emptied instead, making Gemini unavailable rather than wrong:

```
answer   : [mock] no model was called
provider : mock
fallback : gemini (503) GEMINI_API_KEY is not set
```

`503`, retryable, so it moved on.

Two different failures, two different behaviours, both correct — and neither was
a deliberate test.

## When every provider refuses

```python
def _exhausted(attempts: list[Attempt]) -> LLMError:
    if not attempts:
        raise ValueError("no providers configured")

    last = attempts[-1]
    tried = ", ".join(f"{a.provider} ({a.status})" for a in attempts)
    if len(attempts) == 1:
        return LLMError(last.status, last.message, last.provider)
    return LLMError(
        last.status,
        f"every provider refused — tried {tried}. Last: {last.message}",
        last.provider,
    )
```

With one provider, report its error unchanged — wrapping it would only add noise.

With several, name all of them:

```
every provider refused — tried gemini (429), openai (503).
Last: OPENAI_API_KEY is not set
```

That message is doing real work. It says Gemini is out of quota *and* OpenAI has
no key configured. Reporting only the last failure would say "OPENAI_API_KEY is
not set" and hide that the primary provider was exhausted too — sending someone
to fix the wrong thing.

This exact message appeared during the AWS deployment, before the OpenAI key was
added. It told the whole story in one line.

## Pinning disables fallback

```python
order = [provider] if provider else chain()
```

If the caller names a provider, the chain is one item long. No fallback.

That is deliberate, and the test says why:

```python
def test_pinning_a_provider_disables_fallback(calls, monkeypatch):
    """An explicit choice from the model picker is not overridden."""
    seen, behaviour = calls
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "gemini,openai")
    behaviour["gemini"] = LLMError(429, "quota", "gemini")

    with pytest.raises(LLMError):
        generate("prompt", provider="gemini")

    assert seen == ["gemini"]
```

Someone comparing two models pins one deliberately. Silently answering with a
different model would corrupt the comparison and they would never know.

**Automatic behaviour should yield to an explicit choice.**

## Testing without calling anything

```python
@pytest.fixture
def calls(monkeypatch):
    """Record which providers get called, and script what each one does."""
    seen: list[str] = []
    behaviour: dict[str, object] = {}

    def fake_call(prompt: str, provider: str) -> str:
        seen.append(provider)
        outcome = behaviour.get(provider, f"answer from {provider}")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr("rag.llm._call", fake_call)
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    return seen, behaviour
```

`_call` is replaced, so no SDK is touched and no network request happens. The
fixture returns two things:

- `seen` — which providers were called, **in order**
- `behaviour` — a dict to script each provider's outcome

`seen` is the important half. Most of these tests assert on *who was called*, not
on the answer:

```python
def test_a_bad_key_stops_the_chain(calls, monkeypatch):
    """401 is not retryable — it will be 401 at every provider too."""
    seen, behaviour = calls
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "gemini,openai")
    behaviour["gemini"] = LLMError(401, "invalid api key", "gemini")

    with pytest.raises(LLMError) as raised:
        generate("prompt")

    assert raised.value.status == 401
    assert seen == ["gemini"]        # ← openai was never called
```

That last assertion is the test. Without it, a version that fell back on 401 and
then failed anyway would still pass.

## The test that pins the whole point

```python
def test_the_same_prompt_reaches_the_fallback(calls, monkeypatch):
    """The point of falling back: the retrieved passages do not change."""
    prompts: list[str] = []
    _, behaviour = calls
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "gemini,openai")
    behaviour["gemini"] = LLMError(429, "quota", "gemini")

    def recording_call(prompt: str, provider: str) -> str:
        prompts.append(prompt)
        if isinstance(behaviour.get(provider), Exception):
            raise behaviour[provider]
        return "ok"

    monkeypatch.setattr("rag.llm._call", recording_call)
    generate("Notes:\n[1] a passage\n\nQuestion: why?")

    assert len(prompts) == 2
    assert prompts[0] == prompts[1]
```

Two calls, identical prompts.

If someone later refactors this and accidentally re-runs retrieval on the
fallback path, this test fails. Without it, that bug would produce answers that
are *plausible* but grounded in different passages than the citations claim —
the kind of thing nobody notices for months.

## What it looks like when it fires

From the deployed system:

```
● gemini hit its rate limit
  answered with gpt-4o-mini instead, from the same passages

We hold out a validation set to see the split between how well the model
memorises the training data and whether it has learned anything general [1].

answered by gpt-4o-mini
```

Quota ran out, the system moved on, the reader was told, and the answer is still
grounded in the same retrieved passage.

## What this does not solve

**Both providers can be down.** The chain reduces the chance; it does not
eliminate it. `/search` still works, because it never calls a model.

**Fallback costs money.** Gemini is free; OpenAI is not. Every fallback is a
small charge. Fine at this scale, and worth knowing before pointing a chain at a
paid provider under load.

**Answers differ between models.** Same passages, different phrasing. That is why
the byline exists.

---

## What you should take from this chapter

| | |
|---|---|
| Why | 20 generations a day, and retrieval still worked |
| Same context | Nothing re-retrieved — that is what makes it fair |
| The real decision | Which failures are worth retrying elsewhere |
| The question | Is this about the provider, or about the request? |
| Explicit beats automatic | Pinning a model disables fallback |
| Test who was called | Not just what came back |

---

**Next:** [Chapter 18 — Rate limiting](18-rate-limiting.md), where the quota gets
protected from the open internet.
