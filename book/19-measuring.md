# Chapter 19 — Measuring it

**File:** `deploy/bench.py`

## The question a benchmark should answer

Not *"how fast is it?"* — that is a number with nothing to do.

The useful form is: **"is this decision right?"**

The decision here is Chapter 6's. This system compares the question against every
chunk, one by one. A vector database exists to avoid exactly that. So:

> At the size this system actually runs at, is the linear scan a problem?

That question has an answer, and it is measurable.

## What to measure

Two things, and the second matters more.

**Latency against corpus size.** If it grows fast, the scan is a problem.

**Where the time goes inside one query.** A query does two things: turn the
question into a vector, then compare that vector against all the chunks. Only the
second is what an index would speed up. If it is a small part of the total, an
index cannot help much no matter how good it is.

Most benchmarks report the first and skip the second. The second is the one that
decides the architecture.

## The harness

```python
def corpus(target_chunks: int) -> str:
    """Repeat the sample notes until they chunk to roughly `target_chunks`."""
    return " ".join(WORDS * (1 + (target_chunks * 100) // len(WORDS)))


for target in (100, 500, 2000, 5000):
    store = InMemoryStore()

    started = time.perf_counter()
    count = store.add("bench", corpus(target))
    embed_seconds = time.perf_counter() - started

    # The first search pays for lazily loading the query encoder; that is a
    # start-up cost, not a per-query one.
    search_chunks(store, "warm up", k=4)

    latencies = []
    for i in range(30):
        started = time.perf_counter()
        search_chunks(store, f"{QUERY} {i}", k=4)
        latencies.append((time.perf_counter() - started) * 1000)

    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[int(len(latencies) * 0.95) - 1]
```

Four details worth copying into any benchmark you write.

**A warm-up call.** The first search loads the embedding model — several seconds.
That is a start-up cost paid once per process, not a per-query cost. Including it
would make the first measurement meaningless and every conclusion wrong.

**`time.perf_counter()`, not `time.time()`.** A monotonic high-resolution clock.
`time.time()` can jump backwards if the system clock adjusts.

**Thirty runs, not one.** A single measurement catches whatever the CPU was doing
at that instant.

**p50 and p95, not the mean.** The median says what a typical query costs. The
95th percentile says what a slow one costs. An average hides both.

**Vary the query.** `f"{QUERY} {i}"` makes each of the thirty queries different,
so nothing is accidentally cached.

## The result

```
  chunks   embed (s)   chunks/s       p50       p95
----------------------------------------------------
     101        3.27         31     3.7ms     5.5ms
     503        0.94        535     3.8ms     4.2ms
    2002        3.22        623     3.7ms     4.0ms
    5005        7.80        642     3.9ms     4.4ms
```

Read the `p50` column downwards. The corpus grows **fifty-fold**, from 101 chunks
to 5,005, and retrieval goes from 3.7 ms to 3.9 ms.

Essentially flat. That is the surprise, and the second measurement explains it.

> **On the first row:** 31 chunks/second, against 642 on the last. That row
> includes loading the model — a fixed few seconds spread over only 101 chunks.
> Ignore it. The steady-state throughput is the last three rows, around 640/s.
>
> This is the same lesson as the warm-up call, showing up in the data. Fixed
> costs distort small samples.

## Where the time actually goes

```python
started = time.perf_counter()
for _ in range(50):
    query_vector = embed([QUERY])[0]
encode_ms = (time.perf_counter() - started) / 50 * 1000

started = time.perf_counter()
for _ in range(50):
    scores = vectors @ query_vector
    np.argsort(scores)[::-1][:4]
rank_ms = (time.perf_counter() - started) / 50 * 1000
```

```
at 5005 chunks a query splits into:
  encoding the question     4.86 ms
  ranking every chunk       0.08 ms
  ranking is 2% of the work
```

**Ranking five thousand chunks takes 0.08 milliseconds.**

The other 98% is one forward pass through the embedding model to turn the
question into a vector — which happens whether or not you have an index, and
which no vector database touches.

## What this decides

A vector database would optimise the 0.08 ms.

In exchange:

| Cost | |
|---|---|
| A dependency | A client library to install, learn and update |
| A container | Another process to run, monitor and pay for |
| A network hop | Retrieval becomes a call over a socket |
| A failure mode | Something new that can be down |

To save 0.08 ms out of 4.94.

Put like that, it is not a close call. And the argument is now *"here is the
measurement"* rather than *"I did not feel like it."*

## Where the argument stops being true

This part matters as much as the measurement.

The linear scan grows with the corpus. An index does not. Somewhere above 5,000
the two lines cross, and past that the scan is the bottleneck and the answer
flips.

Where? Ranking is roughly linear: 0.08 ms at 5,000 is about 1.6 ms at 100,000 and
16 ms at a million. At a million chunks ranking is several times the encoding
cost, and an index is clearly right.

So the honest claim is narrow:

> At 5,000 chunks the scan is 2% of a query, so an index would save 2%. That
> stops being true somewhere well before a million, and at that point the answer
> changes.

That sentence is the difference between a defensible decision and a prejudice.
"I did not need one at this size, and here is roughly where that stops holding"
is engineering. "Vector databases are overkill" is an opinion that will be wrong
in some other context.

## The embedding side

```
~640 chunks/second
```

At 120 words per chunk, a 50-page document is around 200 chunks — under half a
second to ingest. Not a bottleneck.

But it is a **per-document** cost, paid at ingest, not per query. Different
budget, different concern. The rate matters because it decides whether adding a
document feels instant or feels like a job, and at 640/s it feels instant.

## Run-to-run variance

The numbers in this chapter differ slightly from the ones in the project README —
0.08 ms here, 0.09 ms in an earlier run; 4.86 ms encoding here, 4.00 ms then.

That is normal. Laptop CPUs throttle, other processes compete, and a millisecond
measurement has real noise in it.

It is worth saying rather than tidying away. **A benchmark that reports the same
number every time is usually reporting a cached one.** What is stable here is the
*shape*: encoding dominates, ranking is a rounding error, and latency barely
moves with corpus size. The conclusion survives the noise, which is what makes it
a conclusion.

## Ship the benchmark

`deploy/bench.py` is in the repository. Anyone can run it:

```bash
cd python-service && ./venv/bin/python ../deploy/bench.py
```

Two reasons.

**The claim becomes checkable.** A README that says "retrieval takes 4 ms" asks
to be believed. One that ships the script that produced it does not.

**The decision can be revisited.** When someone loads 50,000 chunks, they run the
same script and see whether the conclusion still holds. A number in prose goes
stale silently; a script goes stale loudly.

## What is not measured

The honest gap, and it is a real one.

**Retrieval quality is not measured.** This chapter measures *speed*. Whether the
right passage comes back is assessed on a handful of examples — Chapter 4's chunk
size, Chapter 7's tests — not on a labelled set.

A proper evaluation needs question/passage pairs with known correct answers, and
metrics like recall@k. There is no such set here, so every quality claim in this
book is "it worked on the examples I tried."

That limit is in the README:

> **Retrieval quality is not measured.** There is no labelled question/passage
> set here, so "it finds the right paragraph" is an observation on a handful of
> examples, not a number.

Being precise about which claims have numbers behind them and which do not is
worth more than having numbers behind all of them.

---

## What you should take from this chapter

| | |
|---|---|
| Benchmark a decision | Not "how fast", but "is this choice right" |
| Warm up first | Or you measure model loading |
| p50 and p95 | The mean hides both |
| Split the query | Encoding 4.86 ms, ranking 0.08 ms — that decides it |
| State where it expires | "At this size" is part of the claim |
| Ship the script | A checkable claim beats a stated one |
| Say what you did not measure | Quality, here |

---

**Next:** [Chapter 20 — Docker](20-docker.md), where the project becomes images
and one of them turns out to be 8.88 GB.
