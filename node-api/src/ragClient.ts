/**
 * Talks to the Python retrieval service over HTTP.
 *
 * Everything that needs the embedding model, NumPy or a language model lives
 * on that side. This file is the only place in the Node service that knows
 * the retrieval service exists.
 */

const BASE_URL = process.env.RAG_SERVICE_URL ?? "http://localhost:8000";

export interface Hit {
  document_id: string;
  text: string;
  score: number;
}

export class RagServiceError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "RagServiceError";
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, init);
  } catch (cause) {
    // The service is down or unreachable — distinct from it rejecting us.
    throw new RagServiceError(503, `retrieval service unreachable at ${BASE_URL}`);
  }

  if (!response.ok) {
    throw new RagServiceError(response.status, await response.text());
  }
  return (await response.json()) as T;
}

const jsonPost = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

export const ragClient = {
  ingest(documentId: string, text: string) {
    return call<{ document_id: string; chunks_added: number }>(
      "/ingest",
      jsonPost({ document_id: documentId, text }),
    );
  },

  search(query: string, k: number) {
    const params = new URLSearchParams({ q: query, k: String(k) });
    return call<{ query: string; hits: Hit[] }>(`/search?${params}`);
  },

  ask(question: string, k: number) {
    return call<{ question: string; answer: string; hits: Hit[] }>(
      "/ask",
      jsonPost({ question, k }),
    );
  },

  deleteDocument(documentId: string) {
    return call<{ document_id: string; chunks_removed: number }>(
      `/documents/${encodeURIComponent(documentId)}`,
      { method: "DELETE" },
    );
  },
};
