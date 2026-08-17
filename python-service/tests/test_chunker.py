from rag.chunker import chunk_text


def test_empty_text_gives_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_short_text_is_one_chunk():
    text = " ".join(["word"] * 50)
    assert len(chunk_text(text, size=120, overlap=20)) == 1


def test_chunks_overlap_by_the_requested_amount():
    words = [str(n) for n in range(300)]
    chunks = chunk_text(" ".join(words), size=100, overlap=20)

    first, second = chunks[0].split(), chunks[1].split()
    # The window advanced by size - overlap = 80 words...
    assert second[0] == "80"
    # ...so the last 20 words of chunk 1 are the first 20 of chunk 2.
    assert first[-20:] == second[:20]


def test_no_trailing_chunk_that_repeats_covered_words():
    # 260 words with a 300-word window: the first window already covers
    # everything, so a second one would be pure duplication.
    text = " ".join(["word"] * 260)
    assert len(chunk_text(text, size=300, overlap=50)) == 1


def test_every_word_appears_somewhere():
    words = [str(n) for n in range(500)]
    chunks = chunk_text(" ".join(words), size=120, overlap=20)

    seen = {word for chunk in chunks for word in chunk.split()}
    assert seen == set(words)


def test_overlap_must_be_smaller_than_size():
    import pytest

    with pytest.raises(ValueError):
        chunk_text("a b c", size=10, overlap=10)
