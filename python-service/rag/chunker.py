"""Split a document into overlapping windows of words.

Why overlap: a sentence that answers a question can sit right on a chunk
boundary. Overlapping the windows means such a sentence stays whole in at
least one chunk.

Why 120 words: measured on the sample notes. At 300 words a chunk covers two
unrelated topics and the best match scored 0.363; at 120 it scored 0.404 and
returned the right passage. Going down to 60 scored marginally higher (0.408)
but returned the *wrong* passage — the chunk no longer held enough context to
be about anything in particular. A higher score is not the goal; retrieving
the right passage is.
"""


def chunk_text(text: str, size: int = 120, overlap: int = 20) -> list[str]:
    """Return `text` as chunks of `size` words, each sharing `overlap` words
    with the previous one."""
    words = text.split()
    if not words:
        return []

    step = size - overlap
    if step <= 0:
        raise ValueError("overlap must be smaller than size")

    chunks = []
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start:start + size]))
        if start + size >= len(words):
            # This window already reached the end of the document; another
            # window would only repeat words we have covered.
            break
    return chunks
