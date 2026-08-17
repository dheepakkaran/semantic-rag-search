"""Ties the pieces together: ingest documents, then search or ask.

    ingest  ->  chunk  ->  embed  ->  store
    search  ->  embed query  ->  rank chunks                     (the "R")
    ask     ->  search  ->  chunks into prompt  ->  generate     (the "AG")

The prompt tells the model to answer only from the supplied notes and to cite
them. Without that instruction the model answers from its own training data,
and there is no way to tell a grounded answer from an invented one.
"""

from .llm import generate
from .retriever import Hit, search
from .store import Store

PROMPT = """Answer the question using only the notes below.
Cite the notes you use like [1] or [2].
If the notes do not contain the answer, say you do not know.

Notes:
{context}

Question: {question}
Answer:"""


def search_chunks(store: Store, query: str, k: int = 4) -> list[Hit]:
    """The retrieval half on its own: which passages match this query?"""
    chunks, vectors = store.load()
    return search(query, chunks, vectors, k)


def ask(store: Store, question: str, k: int = 4) -> tuple[str, list[Hit]]:
    """The full RAG round trip: retrieve passages, then answer from them.

    Returns the answer and the passages it was given, so the caller can show
    the reader what the answer was based on.
    """
    hits = search_chunks(store, question, k)
    if not hits:
        return "No documents have been ingested yet.", []

    context = "\n\n".join(
        f"[{number}] {hit.text}" for number, hit in enumerate(hits, start=1)
    )
    answer = generate(PROMPT.format(context=context, question=question))
    return answer, hits
