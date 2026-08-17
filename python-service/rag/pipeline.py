"""Ties the pieces together: ingest documents, then search or ask.

    ingest  ->  chunk  ->  embed  ->  store
    search  ->  embed query  ->  rank chunks                     (the "R")
    ask     ->  search  ->  chunks into prompt  ->  generate     (the "AG")

The prompt tells the model to answer only from the supplied notes and to cite
them. Without that instruction the model answers from its own training data,
and there is no way to tell a grounded answer from an invented one.

Retrieval runs once. If the first provider refuses — an exhausted daily quota,
most likely — the same prompt goes to the next one, so a fallback answer is
grounded in exactly the same passages.
"""

from dataclasses import dataclass, field

from .llm import Attempt, generate
from .retriever import Hit, search
from .store import Store

PROMPT = """Answer the question using only the notes below.
Cite the notes you use like [1] or [2].
If the notes do not contain the answer, say you do not know.
Write plain prose. Do not use markdown, bullet points or asterisks — the
answer is displayed as text, so any formatting shows up as literal symbols.

Notes:
{context}

Question: {question}
Answer:"""


@dataclass
class Answer:
    """An answer, its sources, and which model produced it."""

    text: str
    hits: list[Hit]
    provider: str = ""
    model: str = ""
    fallbacks: list[Attempt] = field(default_factory=list)


def search_chunks(store: Store, query: str, k: int = 4) -> list[Hit]:
    """The retrieval half on its own: which passages match this query?"""
    chunks, vectors = store.load()
    return search(query, chunks, vectors, k)


def ask(
    store: Store,
    question: str,
    k: int = 4,
    provider: str | None = None,
) -> Answer:
    """The full RAG round trip: retrieve passages, then answer from them.

    Returns the passages alongside the answer, so a caller can show the reader
    what it was based on, and the provider that produced it, so a fallback is
    visible rather than silent.
    """
    hits = search_chunks(store, question, k)
    if not hits:
        return Answer("No documents have been ingested yet.", [])

    context = "\n\n".join(
        f"[{number}] {hit.text}" for number, hit in enumerate(hits, start=1)
    )
    result = generate(PROMPT.format(context=context, question=question), provider)

    return Answer(result.text, hits, result.provider, result.model, result.fallbacks)
