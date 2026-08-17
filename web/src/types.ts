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

export interface SearchResult {
  kind: "search";
  query: string;
  hits: Hit[];
}

export interface AskResult {
  kind: "ask";
  question: string;
  answer: string;
  hits: Hit[];
}

export type Result = SearchResult | AskResult;
