# Chapter 12 — The consistency problem

**File:** `node-api/src/routes.ts`

## The moment two databases stop being free

Chapter 11 justified the split. This chapter is the bill.

Adding a document touches both stores:

```
1. INSERT a row into PostgreSQL          → get document id 7
2. POST the text to the Python service   → it writes 5 chunks into MongoDB
3. UPDATE the PostgreSQL row             → chunk_count = 5
```

Three writes, two databases, and no way to wrap them in a transaction.

## Why not a transaction

A transaction gives you all-or-nothing across several writes. PostgreSQL has
them. MongoDB has them. Neither has one that spans **both** — they are separate
processes with separate logs and no shared coordinator.

Distributed transactions exist. Two-phase commit, sagas, outbox patterns.
They are real engineering with real cost, and they are wildly out of proportion
for a notes app.

So this system does not have atomicity, and the interesting question becomes:
**what happens when step 2 fails?**

## The failure

Step 1 succeeded. There is now a row in PostgreSQL saying document 7 exists.

Step 2 failed — the Python service was restarting, or the embedding model ran out
of memory, or the network hiccuped.

Do nothing and you are left with:

```
PostgreSQL:  id=7, title="Lecture 3", chunk_count=0
MongoDB:     (nothing)
```

A document that appears in the list, opens, claims to exist — and can never
appear in a search result, because it has no chunks. Silently useless.

That is worse than the request having failed cleanly. A visible error is
something a user can act on. A document that exists but never matches anything is
a mystery that erodes trust in every other result.

## The fix: compensate

```typescript
try {
  const inserted = await pool.query<DocumentRow>(
    "insert into documents (title) values ($1) returning *",
    [title],
  );
  const document = inserted.rows[0];

  try {
    const { chunks_added } = await ragClient.ingest(String(document.id), text);
    const updated = await pool.query<DocumentRow>(
      "update documents set chunk_count = $1 where id = $2 returning *",
      [chunks_added, document.id],
    );
    response.status(201).json(updated.rows[0]);
  } catch (error) {
    // PostgreSQL and MongoDB cannot share a transaction, so if embedding
    // fails the metadata row is removed rather than left pointing at
    // nothing. A document that returns no passages is worse than no row.
    await pool.query("delete from documents where id = $1", [document.id]);
    throw error;
  }
} catch (error) {
  next(error);
}
```

If step 2 fails, delete the row from step 1 and re-raise. The user gets an error,
and the system is back where it started.

This is a **compensating action**: you cannot undo the first write atomically, so
you perform a second write that reverses it.

## Why this is not a real fix

It genuinely is not, and the code says so.

Consider: the ingest fails, and the process is killed before the compensating
delete runs. Power loss, container eviction, `kill -9`. The row survives. You are
back to the inconsistent state.

The window is small — microseconds between two `await`s — but it is not zero. And
"small window" is exactly what people say right before a system runs for a year
and hits it.

So the honest description is:

> **Best effort, not a guarantee.** It handles the common failure — the
> downstream service returning an error — and does not handle the rare one, a
> crash between the two writes.

That sentence is in the README's *Honest limits* section, and saying it out loud
is worth more than the code that inspired it.

### What a real fix would look like

Worth knowing, so you can say what you *would* do:

**Write-ahead.** Record the intent ("ingest document 7") in PostgreSQL before
doing anything, and have a background job reconcile records that never completed.
This is the outbox pattern. It survives crashes because the intent is durable.

**One store.** The problem disappears entirely if both writes go to the same
database. That is the strongest argument against the Chapter 11 split, and it
should be said out loud rather than defended around.

Neither was done. The system is small, the failure is rare, and the compensating
delete covers the case that actually happens. That is a decision, and being able
to name the alternatives is what makes it one.

## The test

```typescript
it("removes the metadata row when ingest fails", async () => {
  query
    .mockResolvedValueOnce({ rows: [{ id: 8, title: "Broken", chunk_count: 0 }] })
    .mockResolvedValueOnce({ rowCount: 1 });
  ingest.mockRejectedValueOnce(new RagServiceError(503, "service unreachable"));

  const response = await request(app)
    .post("/api/documents")
    .send({ title: "Broken", text: "some text" });

  expect(response.status).toBe(503);
  // Second call is the compensating delete — no orphan row is left behind.
  expect(query.mock.calls[1][0]).toContain("delete from documents");
  expect(query.mock.calls[1][1]).toEqual([8]);
});
```

Note what it asserts: not just that the response was a 503, but that **the second
database call was a delete, for id 8**. The cleanup is the behaviour under test,
so the test looks at the cleanup.

A test that only checked the status code would pass with the compensating delete
removed. That would be a test that gives false confidence about the exact thing
it appears to cover.

## Ordering matters on delete too

The same problem, mirrored. Deleting a document also touches both stores, and the
order is a real decision:

```typescript
routes.delete("/documents/:id", async (request, response, next) => {
  const id = Number(request.params.id);
  if (!Number.isInteger(id)) {
    return response.status(400).json({ error: "id must be an integer" });
  }

  try {
    // Chunks first: if this fails, the document is still listed and the
    // delete can be retried. The other order would strand the chunks.
    await ragClient.deleteDocument(String(id));

    const { rowCount } = await pool.query("delete from documents where id = $1", [id]);
    if (rowCount === 0) return response.status(404).json({ error: "no such document" });

    response.status(204).end();
  } catch (error) {
    next(error);
  }
});
```

Two possible orders, two different failure modes:

| Order | If the first succeeds and the second fails |
|---|---|
| **Chunks, then metadata** | Document still listed, no chunks. Visible, and retrying fixes it |
| Metadata, then chunks | Chunks orphaned in MongoDB with no document. **Invisible** — they still match searches, labelled "document 4" with no title |

The second is worse, and worse in a specific way: it is invisible. Nothing lists
it, nothing reports it, and the only symptom is a search result citing a document
that no longer exists.

> **General rule: order operations so the failure you cannot avoid is the one you
> can see.**

Neither order is atomic. But one leaves a mess a user notices and can clear, and
the other leaves a mess nobody knows about.

## Where the front end joins in

There is a third piece of state that can go stale: the browser.

```typescript
async function deleteDocument(id: number) {
  setError(null);
  try {
    await api.deleteDocument(id);
    // Whatever is on screen may cite passages from the document that just
    // went away. Leaving it would show sources that can no longer be checked.
    setResult(null);
    await refresh();
  } catch (cause) {
    setError(cause instanceof Error ? cause.message : "could not delete document");
  }
}
```

Delete a document while an answer is on screen and that answer may be citing it.
The passages are still displayed, still look authoritative, and now point at
something that does not exist.

Clearing the result is one line. Without it the interface breaks its own
promise — that every answer can be checked against its sources — quietly.

Consistency is not only a database problem. Anywhere you hold a copy of state,
including a browser tab, it can drift.

---

## What you should take from this chapter

| | |
|---|---|
| The cost of two stores | No transaction spans both |
| Compensating action | A second write that reverses the first |
| Be honest | Best effort — a crash between writes still breaks it |
| Ordering | Fail toward the visible mess, not the invisible one |
| The third store | The browser holds state too, and it goes stale |

---

**Next:** [Chapter 13 — The Node API](13-node-api.md), where a second language
earns its place.
