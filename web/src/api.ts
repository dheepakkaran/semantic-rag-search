/**
 * Every call to the Node API goes through here, so error handling is written
 * once instead of in each component.
 */

import type { AskResult, DocumentRow, Hit, Provider, SearchResult } from "./types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: init?.body ? { "content-type": "application/json" } : undefined,
  });

  if (!response.ok) {
    // The API reports problems as { error, detail? }; fall back to the status
    // line when the body is not JSON at all.
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? body?.error ?? `request failed (${response.status})`);
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export const api = {
  listDocuments() {
    return call<DocumentRow[]>("/documents");
  },

  addDocument(title: string, text: string) {
    return call<DocumentRow>("/documents", {
      method: "POST",
      body: JSON.stringify({ title, text }),
    });
  },

  deleteDocument(id: number) {
    return call<void>(`/documents/${id}`, { method: "DELETE" });
  },

  async search(query: string): Promise<SearchResult> {
    const params = new URLSearchParams({ q: query });
    const body = await call<{ query: string; hits: Hit[] }>(`/search?${params}`);
    return { kind: "search", ...body };
  },

  listProviders() {
    return call<Provider[]>("/providers");
  },

  /** `provider` pins one model; leaving it out allows automatic fallback. */
  async ask(question: string, provider?: string): Promise<AskResult> {
    const body = await call<Omit<AskResult, "kind">>("/ask", {
      method: "POST",
      body: JSON.stringify({ question, provider }),
    });
    return { kind: "ask", ...body };
  },
};
