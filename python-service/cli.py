"""Run the pipeline from the terminal, with no server and no database.

    python cli.py sample_notes.txt search "how does a model learn?"
    python cli.py sample_notes.txt ask    "how does a model learn?"

`search` needs no API key. `ask` calls whichever provider LLM_PROVIDER points
at — use LLM_PROVIDER=mock to exercise the round trip without one.
"""

import sys

from dotenv import load_dotenv

from rag import InMemoryStore, ask, search_chunks

load_dotenv()


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 1

    path, command, query = argv[1], argv[2], argv[3]

    store = InMemoryStore()
    with open(path, encoding="utf-8") as f:
        added = store.add(path, f.read())
    print(f"ingested {added} chunks from {path}\n")

    if command == "search":
        for number, hit in enumerate(search_chunks(store, query), start=1):
            print(f"[{number}] score {hit.score:.3f}")
            print(f"    {hit.text[:200]}...\n")
        return 0

    if command == "ask":
        answer, hits = ask(store, query)
        print(f"Q: {query}\n")
        print(f"A: {answer}\n")
        print("based on:")
        for number, hit in enumerate(hits, start=1):
            print(f"  [{number}] score {hit.score:.3f} — {hit.text[:80]}...")
        return 0

    print(f"unknown command {command!r}; expected 'search' or 'ask'")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
