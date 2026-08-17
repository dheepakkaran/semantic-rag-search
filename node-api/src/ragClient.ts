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

/** A provider that refused before another one answered. */
export interface Attempt {
  provider: string;
  model: string;
  status: number;
  message: string;
}

export interface Provider {
  name: string;
  model: string;
  ready: boolean;
  in_chain: boolean;
}

export interface AskResult {
  question: string;
  answer: string;
  provider: string;
  model: string;
  fallbacks: Attempt[];
  hits: Hit[];
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
    // FastAPI reports problems as { detail }. Unwrap it, so the browser gets
    // "quota exceeded, retry in 34s" rather than that sentence buried inside a
    // stringified JSON body inside another JSON body.
    const body = await response.text();
    let message = body;
    try {
      const parsed = JSON.parse(body) as { detail?: unknown };
      if (typeof parsed.detail === "string") message = parsed.detail;
    } catch {
      // Not JSON — keep the raw text, which is still better than nothing.
    }
    throw new RagServiceError(response.status, message);
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

  /** `provider` pins one model and disables fallback. */
  ask(question: string, k: number, provider?: string) {
    return call<AskResult>("/ask", jsonPost({ question, k, provider }));
  },

  providers() {
    return call<Provider[]>("/providers");
  },

  deleteDocument(documentId: string) {
    return call<{ document_id: string; chunks_removed: number }>(
      `/documents/${encodeURIComponent(documentId)}`,
      { method: "DELETE" },
    );
  },
};
