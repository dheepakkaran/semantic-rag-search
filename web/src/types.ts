export interface DocumentRow {
  id: number;
  title: string;
  chunk_count: number;
  created_at: string;
}

/** A retrieved passage. `title` is filled in by the Node API from PostgreSQL. */
export interface Hit {
  document_id: string;
  title: string | null;
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
  /** A key is present. Not a promise that it has quota left. */
  ready: boolean;
  in_chain: boolean;
}

export interface SearchResult {
  kind: "search";
  query: string;
  hits: Hit[];
}

export interface AskResult {
  kind: "ask";
  question: string;
  answer: string;
  provider: string;
  model: string;
  /** Non-empty when an earlier provider refused and this one stood in. */
  fallbacks: Attempt[];
  hits: Hit[];
}

export type Result = SearchResult | AskResult;
