# Chapter 11 — Two databases, one system

**File:** `python-service/rag/store.py`

## The suspicious decision

This system uses PostgreSQL **and** MongoDB.

Be suspicious of that. Two databases in a student project is usually résumé
padding — a way to get two more words onto a page. The honest default is one
database, and you should need a reason to add a second.

This chapter is that reason, and it also covers the case where the reason does
*not* hold, because that matters just as much.

## What the system stores

Two different kinds of thing, and writing them side by side makes the split
obvious.

**Document metadata**

```
id           1
title        "Lectures 3-5 — Training, Overfitting, Embeddings"
chunk_count  5
created_at   2026-08-17 14:50:47
```

Small. Fixed shape. Every document has exactly these fields. You list them, count
them, sort them by date, and — the important one — **join them against search
results** to label a citation with a title.

**Chunks and their vectors**

```
document_id  "1"
position     3
text         "the family of tricks that push back against overfitting..."
vector       [-0.0439, -0.0025, 0.0163, ... ]      384 numbers
```

Bigger. Variable length text. A 384-number array. No relationships to anything.
You never query these by field — you load them all and do arithmetic.

Those are not the same kind of data, and they are not used the same way.

## Where each one goes

| | Store | Why |
|---|---|---|
| Document metadata | **PostgreSQL** | Relational, fixed shape, joined against results |
| Chunks + vectors | **MongoDB** | Variable-length text and an array, no relationships |

The test for whether this is real or decorative: **can you name a query that
would be awkward in the other store?**

Yes, in both directions.

*Metadata in MongoDB:* the front end needs each citation labelled with its
document title. Search returns `document_id: "1"`. Turning a set of ids into
titles in one operation is what a relational store is for. In a document store
you would be fetching documents by id in a loop, or duplicating the title into
every chunk and updating all of them on rename.

*Vectors in PostgreSQL:* a 384-element array per row, never queried by value,
only ever loaded wholesale. You would be storing it as JSON or an array column
and getting nothing from the relational machinery. It is a blob with an id.

## The honest counter-argument

**You could use one store for both, and for a system this size it would be
fine.**

Everything above is true, and none of it is *forced*. At five documents, either
database handles both jobs without complaint. A single PostgreSQL instance with a
`documents` table and a `chunks` table would work, and would be one less
container.

So the accurate framing is not "two databases were necessary". It is:

> The split follows the grain of the data. It costs one more container and buys a
> cleaner query for citation titles. At a hundred thousand documents that becomes
> a real advantage; at five it is mostly a design statement.

Say that in an interview rather than overselling it. "I split it this way and
here is what it costs" is a stronger answer than "I needed two databases",
because the second one is not true and a good interviewer will find that out in
two questions.

## The interface

The Python service only knows about chunks and vectors. It never touches
PostgreSQL — that belongs to the Node service in Chapter 13.

Storage sits behind three methods:

```python
class Store(Protocol):
    """What the pipeline needs from a store."""

    def add(self, document_id: str, text: str) -> int:
        """Chunk and embed `text`, save it, return how many chunks were added."""

    def load(self) -> tuple[list[Chunk], np.ndarray | None]:
        """Return every chunk and a matching array of vectors."""

    def delete_document(self, document_id: str) -> int:
        """Remove a document's chunks, return how many were removed."""

    def __len__(self) -> int: ...
```

`Protocol` is Python's structural typing. Any class with these methods satisfies
it — no inheritance, no registration. The type checker verifies the shape.

## Two implementations

```python
def build_store() -> Store:
    """MongoStore when MONGO_URI is set, otherwise an in-memory store.

    Falling back to memory means the service still starts with no database,
    which keeps tests and a bare `uvicorn app:app` working.
    """
    uri = os.getenv("MONGO_URI")
    if uri:
        return MongoStore(uri)
    return InMemoryStore()
```

One environment variable decides. That fallback is not a toy:

- **Tests** run against `InMemoryStore` — no container, no cleanup, milliseconds
- **`cli.py`** works with nothing installed but Python
- **A fresh clone** starts and answers questions before you have read the Docker
  chapter

A system that requires infrastructure before it will start is a system people
give up on. The default should be "it runs".

### In memory

```python
class InMemoryStore:
    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._vectors: np.ndarray | None = None

    def add(self, document_id, text, size=120, overlap=20) -> int:
        texts = chunk_text(text, size, overlap)
        if not texts:
            return 0

        vectors = embed(texts)
        self._chunks.extend(Chunk(document_id, t) for t in texts)
        self._vectors = (
            vectors if self._vectors is None else np.vstack([self._vectors, vectors])
        )
        return len(texts)

    def load(self):
        return self._chunks, self._vectors
```

`np.vstack` stacks the new vectors under the existing ones, keeping a single
contiguous array. That matters: Chapter 6's `vectors @ query_vector` is fast
because it operates on one block of memory, not a list of separate arrays.

### In MongoDB

```python
class MongoStore:
    def __init__(self, uri, database="rag", collection="chunks") -> None:
        from pymongo import MongoClient
        self._collection = MongoClient(uri)[database][collection]
        # Lets the Node API delete a document's chunks without a full scan.
        self._collection.create_index("document_id")

    def add(self, document_id, text, size=120, overlap=20) -> int:
        texts = chunk_text(text, size, overlap)
        if not texts:
            return 0

        vectors = embed(texts)
        self._collection.insert_many([
            {
                "document_id": document_id,
                "position": position,
                "text": chunk,
                "vector": vector.tolist(),
            }
            for position, (chunk, vector) in enumerate(zip(texts, vectors))
        ])
        return len(texts)
```

`vector.tolist()` converts the NumPy array to a plain Python list, because BSON
does not know what an `ndarray` is. Coming back out it is a list of floats, which
`np.array(...)` turns back into a matrix.

The index on `document_id` is the one query pattern that is not "load
everything": deleting a document's chunks. Without it, every delete scans the
whole collection.

## Checking what actually landed

Claims about storage are worth verifying rather than assuming:

```bash
docker compose exec -T mongo mongosh --quiet rag --eval '
const d = db.chunks.findOne();
print("chunk documents : " + db.chunks.countDocuments());
print("vector length   : " + d.vector.length);
print("unit length?    : " + Math.sqrt(d.vector.reduce((s,x)=>s+x*x,0)).toFixed(6));
print("indexes         : " + db.chunks.getIndexes().map(i=>i.name).join(", "));
'
```

```
chunk documents : 5
vector length   : 384
unit length?    : 1.000000
indexes         : _id_, document_id_1
```

Five chunks, 384 dimensions, unit length preserved through the round trip, and
the index exists. Chapter 5's normalisation survived being written to a database
and read back — worth confirming, because a store that silently truncated floats
would break Chapter 6's arithmetic in a way no test on the Python side would
catch.

## The limitation, stated plainly

```python
def load(self) -> tuple[list[Chunk], np.ndarray | None]:
    documents = list(self._collection.find({}, {"_id": 0, ...}))
    if not documents:
        return [], None

    chunks = [Chunk(d["document_id"], d["text"]) for d in documents]
    vectors = np.array([d["vector"] for d in documents], dtype=np.float32)
    return chunks, vectors
```

**This reads every vector from MongoDB on every query.**

That is not clever. A production system would keep them in memory and invalidate
on write, or use a database that can do the similarity search itself.

It is written down in the module docstring rather than hidden:

```python
"""
Known limit: `MongoStore.load()` reads every vector on every query. That is
fine into the low thousands of chunks — the read and the dot product together
stay in the low tens of milliseconds. Past that this needs either an
in-process cache or a real vector index; neither is worth adding for a
personal notes collection.
"""
```

Two reasons to write it that way.

**It is true, and someone will find out.** Better they find your note than
discover it themselves and wonder what else is undocumented.

**It states where the decision expires.** "Fine into the low thousands" is a
falsifiable claim with a boundary. That is a different thing from "it's fast
enough", which is an opinion.

## What this bought

The interface is three methods. Because of that:

- Chapter 7's tests use `InMemoryStore` and never touch a database
- Chapter 21's containers use `MongoStore` by setting one variable
- Chapter 26's AWS deployment uses the same image with the same variable

The pipeline code — `search_chunks`, `ask` — does not know which one it has.

That is what a small interface buys. Not flexibility for its own sake: the
ability to run the same logic against a fake in tests and a real database in
production, without branching.

---

## What you should take from this chapter

| | |
|---|---|
| The split | Relational metadata in Postgres; variable-shape blobs in Mongo |
| The test for it | Name a query that would be awkward in the other store |
| The honest part | One store would also work at this size — say so |
| The fallback | No `MONGO_URI` means in-memory, so it always starts |
| The limit | Vectors reload per query; documented, with a boundary |

---

**Next:** [Chapter 12 — The consistency problem](12-consistency.md), where a
write succeeds in one store and fails in the other.
