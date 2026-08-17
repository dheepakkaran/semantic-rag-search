"""Retrieval is tested on its own, without a language model.

That separation is the point: when an answer comes out wrong, the first
question is whether retrieval handed the model the right passage at all. If
these tests pass, the retrieval half is not the problem.
"""

import numpy as np
import pytest

from rag import InMemoryStore, search_chunks

NOTES = {
    "training": (
        "Gradient descent nudges each weight against the slope of the loss. "
        "The size of that step is the learning rate."
    ),
    "overfitting": (
        "Weight decay penalises large weights and dropout switches off units "
        "at random, so the network cannot lean on a single path."
    ),
    "cooking": (
        "Heat the pan until a drop of water skitters across it, then add oil "
        "and let it shimmer before the onions go in."
    ),
}


@pytest.fixture(scope="module")
def store():
    s = InMemoryStore()
    for document_id, text in NOTES.items():
        s.add(document_id, text)
    return s


def test_empty_store_returns_nothing():
    assert search_chunks(InMemoryStore(), "anything") == []


def test_finds_the_right_document_without_sharing_any_keywords(store):
    # "regularisation", "dropout" and "weight decay" are all absent from the
    # question — a keyword search would return nothing here.
    hits = search_chunks(store, "how do I stop my network memorising?", k=1)
    assert hits[0].document_id == "overfitting"


def test_unrelated_question_ranks_the_unrelated_note_last(store):
    hits = search_chunks(store, "how big should the step size be?", k=3)
    assert hits[0].document_id == "training"
    assert hits[-1].document_id == "cooking"


def test_scores_come_back_in_descending_order(store):
    scores = [hit.score for hit in search_chunks(store, "learning rate", k=3)]
    assert scores == sorted(scores, reverse=True)


def test_k_is_capped_at_the_number_of_chunks(store):
    assert len(search_chunks(store, "anything", k=99)) == len(store)


def test_vectors_are_unit_length(store):
    _, vectors = store.load()
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)


def test_deleting_a_document_removes_it_from_results():
    s = InMemoryStore()
    for document_id, text in NOTES.items():
        s.add(document_id, text)

    removed = s.delete_document("overfitting")
    assert removed == 1
    assert len(s) == 2

    found = {hit.document_id for hit in search_chunks(s, "dropout weight decay", k=5)}
    assert "overfitting" not in found
