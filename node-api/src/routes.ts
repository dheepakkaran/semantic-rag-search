/**
 * The REST API the browser talks to.
 *
 *   GET    /api/documents        list ingested documents
 *   POST   /api/documents        add one: metadata here, chunks in the service
 *   DELETE /api/documents/:id    remove metadata and chunks together
 *   GET    /api/search?q=&k=     retrieval only — matching passages
 *   POST   /api/ask              retrieval + a grounded answer
 *
 * Search results come back from the retrieval service carrying a document id
 * but no title, because that service never saw one. Titles are attached here,
 * from PostgreSQL — which is the reason both databases are in the design.
 */

import { Router } from "express";

import { pool, type DocumentRow } from "./db.js";
import { ragClient, RagServiceError, type Hit } from "./ragClient.js";

export const routes = Router();

interface TitledHit extends Hit {
  title: string | null;
}

/** Attach each hit's document title in one query, not one query per hit. */
async function withTitles(hits: Hit[]): Promise<TitledHit[]> {
  const ids = [
    ...new Set(hits.map((hit) => Number(hit.document_id)).filter(Number.isInteger)),
  ];
  if (ids.length === 0) {
    return hits.map((hit) => ({ ...hit, title: null }));
  }

  const { rows } = await pool.query<{ id: number; title: string }>(
    "select id, title from documents where id = any($1::int[])",
    [ids],
  );
  const titles = new Map(rows.map((row) => [String(row.id), row.title]));

  return hits.map((hit) => ({ ...hit, title: titles.get(hit.document_id) ?? null }));
}

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function readK(value: unknown): number {
  const k = Number(value ?? 4);
  if (!Number.isInteger(k) || k < 1 || k > 10) return 4;
  return k;
}

routes.get("/health", (_request, response) => {
  response.json({ status: "ok" });
});

/** Feeds the model picker: which providers exist and which have a key. */
routes.get("/providers", async (_request, response, next) => {
  try {
    response.json(await ragClient.providers());
  } catch (error) {
    next(error);
  }
});

routes.get("/documents", async (_request, response, next) => {
  try {
    const { rows } = await pool.query<DocumentRow>(
      "select * from documents order by created_at desc",
    );
    response.json(rows);
  } catch (error) {
    next(error);
  }
});

routes.post("/documents", async (request, response, next) => {
  const title = readString(request.body?.title);
  const text = readString(request.body?.text);

  if (!title) return response.status(400).json({ error: "title is required" });
  if (!text) return response.status(400).json({ error: "text is required" });

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
});

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

routes.get("/search", async (request, response, next) => {
  const query = readString(request.query.q);
  if (!query) return response.status(400).json({ error: "q is required" });

  try {
    const { hits } = await ragClient.search(query, readK(request.query.k));
    response.json({ query, hits: await withTitles(hits) });
  } catch (error) {
    next(error);
  }
});

routes.post("/ask", async (request, response, next) => {
  const question = readString(request.body?.question);
  if (!question) return response.status(400).json({ error: "question is required" });

  const provider =
    typeof request.body?.provider === "string" ? request.body.provider : undefined;

  try {
    const result = await ragClient.ask(question, readK(request.body?.k), provider);
    response.json({
      question,
      answer: result.answer,
      // Which model actually answered, and who refused first — so a fallback
      // is visible in the UI rather than silently swapped in.
      provider: result.provider,
      model: result.model,
      fallbacks: result.fallbacks,
      hits: await withTitles(result.hits),
    });
  } catch (error) {
    next(error);
  }
});

export { RagServiceError };
