# Chapter 16 — Accessibility

**File:** `web/src/styles.css`

## Looking is not checking

The interface from Chapter 15 looked fine. Clean greys, plenty of whitespace,
nothing obviously wrong.

Then the colours were measured, and three of them failed the standard — one of
them badly.

That gap is the point of this chapter. **You cannot assess contrast by looking at
it**, because you are looking at a good screen, at full brightness, indoors, with
your own eyesight. The person who cannot read your grey text is not in the room.

## The standard

WCAG defines contrast as a ratio between two colours, from 1:1 (identical) to
21:1 (black on white).

| Content | Minimum |
|---|---|
| Normal text | **4.5:1** |
| Large text (≥ 24 px, or ≥ 19 px bold) | **3:1** |
| UI component boundaries — an input's border | **3:1** |

That third row is the one people miss. It is WCAG 1.4.11, and it applies to the
edges that tell you where a control is.

## Measuring it

The formula is not something to eyeball, so here it is as code:

```python
def lum(hex_):
    h = hex_.lstrip('#')
    c = [int(h[i:i+2], 16)/255 for i in (0, 2, 4)]
    c = [x/12.92 if x <= 0.04045 else ((x+0.055)/1.055)**2.4 for x in c]
    return 0.2126*c[0] + 0.7152*c[1] + 0.0722*c[2]

def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)
```

Two things worth noticing.

**The green coefficient is 0.7152.** Human eyes are far more sensitive to green
than to blue (0.0722). Perceived brightness is not the average of the channels.

**The gamma correction.** sRGB values are not linear in brightness — the piecewise
function converts them to linear light before weighting. Skip it and every number
is wrong.

## The results

```
colour      var            vs page   AA normal(4.5)  AA large(3.0)
#262627     --ink           14.99:1   PASS            PASS
#4a4a4d     --ink-soft       8.76:1   PASS            PASS
#8a8a91     --muted          3.40:1   FAIL            PASS
#c9c9ce     placeholder      1.64:1   FAIL            FAIL
#e4e4e6     --hairline       1.26:1   FAIL            FAIL
```

Three failures, and they were not equally bad.

### Failure 1 — `--muted` at 3.40:1

This one was everywhere. The wordmark, the eyebrow labels, the similarity scores,
the "Press Enter" hint, the section headings, every hint in the notes panel.

All small text. All needing 4.5:1. All at 3.40.

Not invisible — readable on a good screen. Which is exactly why it survived
review: it looked fine to the person who chose it.

### Failure 2 — the placeholder at 1.64:1

The worst number in the table, in the largest text on the page.

The placeholder in the hero input is around 34 px, so the 3:1 large-text
threshold applies. At 1.64:1 it missed by a wide margin — the text that tells a
first-time visitor what the box is for was the least legible thing on screen.

### Failure 3 — the input's underline at 1.26:1

The subtlest one, and the most interesting.

Chapter 15's input is a rule rather than a box. That rule is not decoration — it
is the *only* thing indicating where the input is. It is the control's boundary,
so WCAG 1.4.11 applies and it needs 3:1.

At 1.26:1 it was nearly invisible against the background. Someone who could not
see it would be looking at a page with no obvious place to type.

## Choosing replacements

Not "make it darker" — measure candidates and pick the lightest that passes:

```
candidate replacements:
  #7a7a83  4.22:1     ← still fails 4.5
  #74747d  4.59:1     ← passes
  #6e6e77  5.01:1
  #6b6b73  5.24:1
```

`#74747d` at 4.59:1 was chosen. Anything darker passes too, but the design wants
the muted text to *look* muted. The lightest passing value preserves the
intention and meets the standard.

For the border, the same exercise against the 3:1 threshold:

```
  #a3a3ab  2.48:1   FAIL
  #93939c  3.02:1   PASS     ← chosen
  #8a8a91  3.40:1   PASS
```

## The fix

```css
:root {
  --ink: #262627;
  --ink-soft: #4a4a4d;
  --muted: #74747d;      /* 4.59:1 on --page — AA for normal text (was #8a8a91, 3.40:1) */
  --placeholder: #8a8a91; /* 3.40:1 — AA for the large hero input only */
  --rule: #93939c;        /* 3.02:1 — WCAG 1.4.11 minimum for an input's boundary */
  --hairline: #e4e4e6;    /* decorative dividers only */
}
```

Three new variables, and the comments carry the measured number and the rule it
satisfies. That is deliberate: the next person who thinks the grey is too dark
can see it is not a preference.

Note that `--hairline` stays at 1.26:1. It is still used — for the dividers
between search results and the border of the notes-panel inputs' container. Those
are decorative separators, not control boundaries, and decoration has no contrast
requirement.

Distinguishing the two is the actual skill. "Make everything darker" would have
flattened a design that uses lightness deliberately.

## Confirming it in the running app

```javascript
getComputedStyle(document.querySelector('.wordmark')).color
// → "rgb(116, 116, 125)"    #74747d ✓

getComputedStyle(document.querySelector('.big-input')).borderBottomColor
// → "rgb(147, 147, 156)"    #93939c ✓
```

Checking the computed value rather than the source catches a whole class of
mistake — a variable defined but never applied, or overridden later in the
cascade.

## Four things that are not contrast

Accessibility is broader than colour. Four more changes, none expensive.

### Errors are announced

```typescript
{error && <p className="error" role="alert">{error}</p>}
```

`role="alert"` makes a screen reader speak the message when it appears. Without
it the error is drawn and never mentioned, and a user who cannot see it has no
idea the request failed.

### Answers are announced politely

```typescript
<div aria-live="polite" aria-busy={busy}>
  {result && <ResultPanel result={result} hasDocuments={documents.length > 0} />}
</div>
```

`polite` waits for a pause rather than interrupting. `aria-busy` says a request
is in flight, so the reader is not told about a half-rendered state.

### The score bar is hidden from screen readers

```typescript
{/* The bar restates the number visually, so it is hidden from
    screen readers rather than announced twice. */}
<span className="score-track" aria-hidden="true">
  <span className="score-fill" style={{ width: `${fraction * 100}%` }} />
</span>
<span title="cosine similarity">{hit.score.toFixed(3)}</span>
```

The bar and the number carry identical information. Announcing both is noise, so
the decorative one is hidden.

`aria-hidden` is easy to misuse — hiding something that carries unique
information makes things worse. The test is: *does anything disappear if this is
hidden?* Here, no. The number is right beside it.

### Motion can be turned off

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

Six lines. Some people get motion sickness from animation and set this preference
at the operating system level. Honouring it costs nothing and the alternative is
making a subset of users physically unwell.

### Focus rings for keyboard users only

```css
/* Keyboard users get a visible focus ring; mouse users do not see one. */
:focus-visible {
  outline: 2px solid var(--ink);
  outline-offset: 3px;
}
```

`:focus-visible` shows the ring when focus arrives by keyboard and not by mouse
click. This is the modern answer to the old bad habit of `outline: none`, which
made interfaces look tidy and rendered them unusable without a mouse.

## Why this belongs in a project like this

Two honest reasons.

**It is cheap.** Every fix in this chapter is a colour value or one attribute.
The measuring script took ten minutes to write. There is no version of this
project where the effort was better spent elsewhere.

**It is checkable.** *"I made it accessible"* is a claim. *"`--muted` was 3.40:1
against a 4.5:1 requirement; it is now 4.59:1"* is a measurement, and it is the
same kind of statement as the chunk-size decision in Chapter 4 and the latency
measurement in Chapter 19.

That is the thread running through this whole book: **the decisions worth
defending are the ones with a number behind them.**

---

## What you should take from this chapter

| | |
|---|---|
| You cannot see contrast | Your screen, your eyes, your lighting |
| The three thresholds | 4.5 normal, 3 large, 3 for control boundaries |
| Three failures found | 3.40, 1.64, 1.26 — all looked fine |
| Pick the lightest that passes | Keep the design intent, meet the standard |
| Decoration is exempt | Dividers are not control boundaries |
| Beyond colour | `role="alert"`, `aria-live`, `aria-hidden`, reduced motion, `:focus-visible` |

---

**Next:** [Chapter 17 — Falling back](17-fallback.md), where the system learns
which failures are worth retrying somewhere else.
