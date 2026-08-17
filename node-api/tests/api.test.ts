/**
 * Route tests with PostgreSQL and the retrieval service both mocked.
 *
 * Nothing here needs a database or a running Python service, so these run on
 * every push. What is being tested is this service's own logic: input
 * validation, attaching titles to hits, and the cleanup when ingest fails
 * after the metadata row is already written.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import request from "supertest";

const query = vi.fn();
const ingest = vi.fn();
const search = vi.fn();
const ask = vi.fn();
const deleteDocument = vi.fn();

vi.mock("../src/db.js", () => ({
  pool: { query: (...args: unknown[]) => query(...args) },
  initSchema: vi.fn(),
}));

vi.mock("../src/ragClient.js", async () => {
  class RagServiceError extends Error {
    constructor(
      public readonly status: number,
      message: string,
    ) {
      super(message);
      this.name = "RagServiceError";
    }
  }
  return {
    RagServiceError,
    ragClient: {
      ingest: (...a: unknown[]) => ingest(...a),
      search: (...a: unknown[]) => search(...a),
      ask: (...a: unknown[]) => ask(...a),
      deleteDocument: (...a: unknown[]) => deleteDocument(...a),
    },
  };
});

const { createApp } = await import("../src/app.js");
const { RagServiceError } = await import("../src/ragClient.js");
const app = createApp();

beforeEach(() => {
  vi.clearAllMocks();
});

describe("GET /api/documents", () => {
  it("returns the rows from PostgreSQL", async () => {
    query.mockResolvedValueOnce({
      rows: [{ id: 1, title: "Lecture 3", chunk_count: 5, created_at: "2026-09-01" }],
    });

    const response = await request(app).get("/api/documents");

    expect(response.status).toBe(200);
    expect(response.body).toHaveLength(1);
    expect(response.body[0].title).toBe("Lecture 3");
  });
});

describe("POST /api/documents", () => {
  it("stores metadata, ingests the text, then saves the chunk count", async () => {
    query
      .mockResolvedValueOnce({ rows: [{ id: 7, title: "Lecture 3", chunk_count: 0 }] })
      .mockResolvedValueOnce({ rows: [{ id: 7, title: "Lecture 3", chunk_count: 5 }] });
    ingest.mockResolvedValueOnce({ document_id: "7", chunks_added: 5 });

    const response = await request(app)
      .post("/api/documents")
      .send({ title: "Lecture 3", text: "gradient descent nudges each weight" });

    expect(response.status).toBe(201);
    expect(response.body.chunk_count).toBe(5);
    expect(ingest).toHaveBeenCalledWith("7", "gradient descent nudges each weight");
  });

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

  it.each([
    ["missing title", { text: "some text" }],
    ["missing text", { title: "Lecture 3" }],
    ["blank title", { title: "   ", text: "some text" }],
  ])("rejects %s", async (_name, payload) => {
    const response = await request(app).post("/api/documents").send(payload);

    expect(response.status).toBe(400);
    expect(ingest).not.toHaveBeenCalled();
  });
});

describe("GET /api/search", () => {
  it("attaches document titles to the hits", async () => {
    search.mockResolvedValueOnce({
      hits: [
        { document_id: "1", text: "dropout switches off units", score: 0.51 },
        { document_id: "2", text: "the learning rate is the step size", score: 0.32 },
      ],
    });
    query.mockResolvedValueOnce({
      rows: [
        { id: 1, title: "Overfitting" },
        { id: 2, title: "Training" },
      ],
    });

    const response = await request(app).get("/api/search?q=how to stop memorising");

    expect(response.status).toBe(200);
    expect(response.body.hits[0].title).toBe("Overfitting");
    expect(response.body.hits[1].title).toBe("Training");
    // One lookup for all hits, not one per hit.
    expect(query).toHaveBeenCalledTimes(1);
  });

  it("requires a query", async () => {
    const response = await request(app).get("/api/search?q=  ");

    expect(response.status).toBe(400);
    expect(search).not.toHaveBeenCalled();
  });

  it("falls back to k=4 when k is out of range", async () => {
    search.mockResolvedValueOnce({ hits: [] });

    await request(app).get("/api/search?q=anything&k=99");

    expect(search).toHaveBeenCalledWith("anything", 4);
  });
});

describe("POST /api/ask", () => {
  it("returns the answer together with the passages it cited", async () => {
    ask.mockResolvedValueOnce({
      answer: "Dropout and weight decay [1].",
      hits: [{ document_id: "1", text: "dropout switches off units", score: 0.51 }],
    });
    query.mockResolvedValueOnce({ rows: [{ id: 1, title: "Overfitting" }] });

    const response = await request(app)
      .post("/api/ask")
      .send({ question: "how do I stop my network memorising?" });

    expect(response.status).toBe(200);
    expect(response.body.answer).toContain("Dropout");
    expect(response.body.hits[0].title).toBe("Overfitting");
  });

  it("passes the retrieval service's status code through", async () => {
    ask.mockRejectedValueOnce(new RagServiceError(503, "GEMINI_API_KEY is not set"));

    const response = await request(app).post("/api/ask").send({ question: "anything" });

    expect(response.status).toBe(503);
    expect(response.body.detail).toContain("GEMINI_API_KEY");
  });
});

describe("DELETE /api/documents/:id", () => {
  it("removes the chunks before the metadata row", async () => {
    deleteDocument.mockResolvedValueOnce({ document_id: "3", chunks_removed: 5 });
    query.mockResolvedValueOnce({ rowCount: 1 });

    const response = await request(app).delete("/api/documents/3");

    expect(response.status).toBe(204);
    expect(deleteDocument).toHaveBeenCalledWith("3");
  });

  it("404s for an unknown id", async () => {
    deleteDocument.mockResolvedValueOnce({ document_id: "99", chunks_removed: 0 });
    query.mockResolvedValueOnce({ rowCount: 0 });

    expect((await request(app).delete("/api/documents/99")).status).toBe(404);
  });

  it("rejects a non-numeric id", async () => {
    const response = await request(app).delete("/api/documents/abc");

    expect(response.status).toBe(400);
    expect(deleteDocument).not.toHaveBeenCalled();
  });
});

describe("unknown routes", () => {
  it("404s", async () => {
    expect((await request(app).get("/nope")).status).toBe(404);
  });
});
