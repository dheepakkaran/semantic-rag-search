"""Measure embedding throughput and retrieval latency against corpus size.

    cd python-service && ./venv/bin/python ../deploy/bench.py

Produces the numbers in the README's Performance section. The interesting one
is the split at the end: how much of a query is encoding the question, and how
much is ranking every chunk. That ratio is the argument for or against adding
a vector index, and it is worth re-running rather than assuming.
"""

import statistics
import sys
import time
from pathlib import Path

SERVICE = Path(__file__).resolve().parent.parent / "python-service"
sys.path.insert(0, str(SERVICE))

import numpy as np  # noqa: E402

from rag import InMemoryStore, search_chunks  # noqa: E402
from rag.embedder import embed  # noqa: E402

WORDS = (SERVICE / "sample_notes.txt").read_text(encoding="utf-8").split()
QUERY = "how do I stop my network memorising?"


def corpus(target_chunks: int) -> str:
    """Repeat the sample notes until they chunk to roughly `target_chunks`."""
    return " ".join(WORDS * (1 + (target_chunks * 100) // len(WORDS)))


def main() -> None:
    print(f"{'chunks':>8}  {'embed (s)':>10}  {'chunks/s':>9}  {'p50':>8}  {'p95':>8}")
    print("-" * 52)

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
        print(
            f"{count:>8}  {embed_seconds:>10.2f}  {count / embed_seconds:>9.0f}"
            f"  {p50:>6.1f}ms  {p95:>6.1f}ms"
        )

    # Where does a query actually spend its time?
    store = InMemoryStore()
    store.add("bench", corpus(5000))
    chunks, vectors = store.load()

    started = time.perf_counter()
    for _ in range(50):
        query_vector = embed([QUERY])[0]
    encode_ms = (time.perf_counter() - started) / 50 * 1000

    started = time.perf_counter()
    for _ in range(50):
        scores = vectors @ query_vector
        np.argsort(scores)[::-1][:4]
    rank_ms = (time.perf_counter() - started) / 50 * 1000

    print(f"\nat {len(chunks)} chunks a query splits into:")
    print(f"  encoding the question   {encode_ms:6.2f} ms")
    print(f"  ranking every chunk     {rank_ms:6.2f} ms")
    print(f"  ranking is {rank_ms / (encode_ms + rank_ms) * 100:.0f}% of the work")


if __name__ == "__main__":
    main()
