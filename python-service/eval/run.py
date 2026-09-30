"""Does retrieval actually find the right passage?

Everything else in this project measures speed. This measures whether the
thing is correct, which is the question that matters when an answer comes out
wrong: was the model handed the right passage at all?

    ./venv/bin/python eval/run.py

Twenty questions, each labelled with a phrase that only appears in the passage
that answers it. A question is *hit at k* when that phrase is inside one of
the top k retrieved passages.

    recall@1   how often the very best passage is the right one
    recall@4   how often the right one is among the four the model sees
    MRR        1/rank of the right passage, averaged — rewards ranking it high

recall@4 is the number that matters most, because four is what `ask()` puts in
the prompt. recall@1 matters for the MCP path, where a client may only read
the first result.

The questions are written to share as few words as possible with the passage
they point at — "how do I stop my network memorising?" for the passage about
weight decay and dropout. A keyword search would score close to zero here, so
this measures the embedding rather than an accidental word overlap.

Honest limit: twenty questions over one document, written by the same person
who wrote the system. That is enough to catch a regression and not enough to
claim a quality number. A real evaluation needs questions someone else wrote.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag import InMemoryStore, search_chunks  # noqa: E402

K = 4
FLOOR = 0.90  # recall@4 below this fails the run, so CI catches a regression

ROOT = Path(__file__).resolve().parent.parent.parent
QUESTIONS = Path(__file__).resolve().parent / "questions.jsonl"


def load_store() -> InMemoryStore:
    """The seed notes, plus distractors.

    Without them the corpus is five chunks and k is four, so recall@4 is 1.00
    by arithmetic rather than by retrieval working. distractors.txt adds
    unrelated technical passages — indexes, caching, git, decision trees,
    k-means, rate limiting, queues — several of which are close enough in
    register to be plausible wrong answers.
    """
    store = InMemoryStore()
    for path in sorted((ROOT / "seed").glob("*.txt")):
        store.add(path.stem.replace("_", " "), path.read_text(encoding="utf-8"))

    distractors = Path(__file__).resolve().parent / "distractors.txt"
    store.add("distractors", distractors.read_text(encoding="utf-8"))
    return store


def rank_of_expected(hits, expect: str) -> int | None:
    """1-based position of the passage containing `expect`, or None."""
    for position, hit in enumerate(hits, start=1):
        if expect.lower() in hit.text.lower():
            return position
    return None


def main() -> int:
    store = load_store()
    cases = [json.loads(line) for line in QUESTIONS.read_text().splitlines() if line.strip()]

    ranks: list[int | None] = []
    misses: list[tuple[str, str, str]] = []

    for case in cases:
        hits = search_chunks(store, case["question"], K)
        rank = rank_of_expected(hits, case["expect"])
        ranks.append(rank)
        if rank is None:
            got = hits[0].text[:70].replace("\n", " ") if hits else "nothing"
            misses.append((case["question"], case["expect"], got))

    found = [r for r in ranks if r is not None]
    recall_1 = sum(1 for r in ranks if r == 1) / len(ranks)
    recall_k = len(found) / len(ranks)
    mrr = sum(1 / r for r in found) / len(ranks)

    print(f"{len(cases)} questions over {len(store)} chunks\n")
    print(f"  recall@1   {recall_1:.2f}")
    print(f"  recall@{K}   {recall_k:.2f}")
    print(f"  MRR        {mrr:.3f}")

    if misses:
        print(f"\n  missed ({len(misses)}):")
        for question, expect, got in misses:
            print(f"    {question}")
            print(f"      wanted a passage with: {expect!r}")
            print(f"      best was            : {got}...")

    if recall_k < FLOOR:
        print(f"\nrecall@{K} {recall_k:.2f} is below the {FLOOR:.2f} floor")
        return 1

    print(f"\nrecall@{K} is at or above the {FLOOR:.2f} floor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
