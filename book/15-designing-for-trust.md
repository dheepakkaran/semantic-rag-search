# Chapter 15 — Designing for trust

**Files:** `web/src/components/ResultPanel.tsx`, `web/src/styles.css`

## The problem this interface has

An answer from a language model looks the same whether it is true or invented.
Same confident tone, same fluent prose, same absence of hedging.

The reader cannot tell by looking. So the interface has one job beyond showing
the answer: **make it checkable in seconds.**

Every decision in this chapter comes from that.

## Decision 1: sources are never hidden

```typescript
{result.kind === "ask" && (
  <>
    <p className="answer">{result.answer}</p>
    {result.model && (
      <p className="byline">answered by <strong>{result.model}</strong></p>
    )}
    <h2 className="section-label">Grounded on</h2>
  </>
)}
```

Then the passages, always, immediately below.

The obvious alternative is a *"show sources"* disclosure. It is tidier and most
products do it. It was rejected, and the reason is in the component's docstring:

```typescript
/**
 * The passages are always visible, never collapsed behind a disclosure. An
 * answer you cannot check against its sources is indistinguishable from one
 * the model invented.
 */
```

A disclosure makes checking *optional*, and optional means almost nobody does it.
The whole value of RAG over asking a model directly is that the answer is
verifiable. Hiding the verification behind a click gives that away for tidiness.

The cost is a longer page. That is the right trade for this application.

## Decision 2: say which model answered

```
answered by gpt-4o-mini
```

Small grey text under every answer.

This matters because the model can change between one question and the next —
Chapter 17 falls back automatically when a provider runs out of quota. Without
the byline, you could ask the same question twice, get two different answers, and
have no idea why.

It also makes a comparison possible. Pin the picker to one model, ask; pin it to
another, ask again. The retrieved passages are identical, so any difference is
the model. That is a genuinely useful thing to be able to do, and it costs one
line of text.

## Decision 3: show the fallback, do not hide it

```typescript
function FallbackNotice({ result }: { result: AskResult }) {
  return (
    <div className="fallback rise-sm" role="status">
      <span className="fallback-mark" aria-hidden="true" />
      <span>
        {result.fallbacks.map((attempt) => (
          <span key={attempt.provider} className="fallback-line">
            <strong>{attempt.provider}</strong>{" "}
            {attempt.status === 429 ? "hit its rate limit" : `refused (${attempt.status})`}
          </span>
        ))}
        <span className="fallback-line">
          answered with <strong>{result.model}</strong> instead, from the same passages
        </span>
      </span>
    </div>
  );
}
```

Which renders:

> ● **gemini** hit its rate limit
> answered with **gpt-4o-mini** instead, from the same passages

The engineering instinct is to make fallback invisible — it worked, why bother
the user? But the answer came from a different model than the one selected, and
someone comparing two answers deserves to know that.

The phrase **"from the same passages"** is doing specific work. It tells the
reader the retrieval did not change, so any difference they notice is the model
and not the sources. Without it, a fallback looks like the system quietly did
something else entirely.

## Decision 4: a slow pulse, not a warning

```css
/* A slow pulse, not a warning triangle. Falling back worked — it is worth
   mentioning, not worth alarming anyone about. */
@keyframes breathe {
  0%, 100% { opacity: 0.35; transform: scale(0.82); }
  50%      { opacity: 1;    transform: scale(1); }
}

.fallback-mark {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--ink);
  animation: breathe 2.4s ease-in-out infinite;
}
```

The obvious choice for "something unusual happened" is a warning triangle in
amber. That would be wrong. Nothing failed — the system did exactly what it was
designed to do and produced a good answer.

A small dot with a slow 2.4-second pulse reads as *"note this"* rather than
*"something is wrong"*. Tone is part of correctness: an interface that cries wolf
at working behaviour trains people to ignore it when something actually breaks.

## Decision 5: a bar that sweeps rather than fills

```css
/* A bar that sweeps rather than fills: the wait has no known duration, and a
   progress bar that guesses is a small lie. */
@keyframes sweep {
  from { transform: translateX(-100%); }
  to   { transform: translateX(280%); }
}
```

```typescript
{busy && mode === "ask" ? (
  <span className="waiting" aria-hidden="true">
    <span className="waiting-track"><span className="waiting-fill" /></span>
    asking {provider ?? providers.find((p) => p.in_chain && p.ready)?.name ?? "the model"}
  </span>
) : (
  <span className="enter-hint">Press <kbd>Enter</kbd> ↵</span>
)}
```

A progress bar that fills claims to know how far along it is. This request could
take two seconds or twelve, depending on the provider, the length, and whether a
fallback is about to happen. A filling bar would be inventing that number.

A sweeping bar says *"working"* and claims nothing else. And the text beside it
says which provider is being waited on — the specific thing a reader wants to
know while waiting.

## Decision 6: scores get a bar and a number

```typescript
// Cosine similarity, so 1.00 is identical and 0.00 unrelated. Cosine can go
// negative, hence the clamp before it becomes a width.
const fraction = Math.max(0, Math.min(1, hit.score));
```

```
Lectures 3-5 — Training, Overfitting, Embeddings        ▬▬▬▭▭▭  0.569
```

The number is exact; the bar is comparable at a glance. Four hits, and you can
see immediately whether the top one is far ahead or whether they are all
mediocre — which tells you how much to trust the answer.

The clamp is a real bug prevented. A negative cosine would produce a negative CSS
width, which browsers ignore silently. The bar would just not render, and nothing
anywhere would report a problem.

## Decision 7: the empty state says which emptiness

```typescript
<p className="muted">
  {hasDocuments
    ? "Nothing in your notes came close to that."
    : "There are no notes to search yet — add some from the Notes panel."}
</p>
```

No results has two entirely different causes:

- You have notes, and none match → *your notes do not cover this*
- You have no notes → *you have not added anything yet*

One message for both would be actively unhelpful in the second case, where the
user is told their notes do not contain something when they have no notes at all.

Distinguishing them costs one boolean prop.

## Where the visual language came from

The interface borrows from Typeform: one thing in focus at a time, large
conversational type, a narrow centred column, an input that is a rule rather than
a box, a single near-black accent, and motion that carries new content in from
below.

```css
/* A rule, not a box — the Typeform input treatment. */
.big-input {
  border: none;
  border-bottom: 2px solid var(--rule);
  font-size: clamp(1.5rem, 4.2vw, 2.15rem);
  font-weight: 500;
  letter-spacing: -0.02em;
}
```

What was **not** borrowed matters as much. Typeform's defining pattern is one
question at a time with a progress bar. This app asks one question, so there are
no steps and no progress to show. Copying the progress bar would have been
copying the appearance of a mechanic that does not exist here.

```css
/* Visual language borrowed from Typeform: ...
   What is deliberately not borrowed: the multi-step flow and progress bar.
   This app asks one question, so there is no progress to show. */
```

> Borrowing a design language means taking the reasoning, not the components. A
> progress bar with nothing to measure is decoration pretending to be
> information.

## The layout moves once

```css
.stage {
  display: flex;
  flex-direction: column;
  justify-content: center;   /* hero: vertically centred */
}

.stage.answered {
  justify-content: flex-start;
  padding-top: 1rem;
}
```

Before you ask, the question box sits in the middle of the screen — nothing else
competes for attention. Once there is an answer, it moves to the top and the
answer gets the space.

One class, two states, and the interface reorganises around whatever matters at
that moment.

> A small bug lived here for a while: the original CSS had
> `transition: justify-content 0.3s`. `justify-content` is not an animatable
> property, so the declaration did nothing at all. It was removed. Dead CSS is
> not harmful, but it is a false claim about how the interface behaves — the next
> person reads it and believes there is an animation to debug.

---

## What you should take from this chapter

| | |
|---|---|
| The job | Make an answer checkable in seconds |
| Sources | Always visible — optional checking means no checking |
| Fallback | Shown, with "from the same passages" |
| Tone | A pulse, not a warning — do not cry wolf at working behaviour |
| Waiting | Sweep, do not fill — a guessed percentage is a lie |
| Empty states | Two causes, two messages |
| Borrowing | Take the reasoning, not the components |

---

**Next:** [Chapter 16 — Accessibility](16-accessibility.md), where three
failures are found by measuring rather than looking.
