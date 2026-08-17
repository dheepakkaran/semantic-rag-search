import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "./api";
import { DocumentPanel } from "./components/DocumentPanel";
import { ResultPanel } from "./components/ResultPanel";
import type { DocumentRow, Result } from "./types";

type Mode = "ask" | "search";

export default function App() {
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<Mode>("ask");
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      setDocuments(await api.listDocuments());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "could not load documents");
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function run(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim() || busy) return;

    setBusy(true);
    setError(null);
    try {
      setResult(mode === "ask" ? await api.ask(query.trim()) : await api.search(query.trim()));
    } catch (cause) {
      setResult(null);
      setError(cause instanceof Error ? cause.message : "request failed");
    } finally {
      setBusy(false);
      // The input is disabled while waiting, which drops focus; put it back so
      // the next question can be typed straight away.
      inputRef.current?.focus();
    }
  }

  async function addDocument(title: string, text: string) {
    setError(null);
    try {
      await api.addDocument(title, text);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "could not add document");
    }
  }

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

  const empty = loaded && documents.length === 0;

  return (
    <div className="app">
      <header className="topbar">
        <span className="wordmark">Semantic RAG Search</span>
        <button
          type="button"
          className="notes-toggle"
          aria-expanded={notesOpen}
          onClick={() => setNotesOpen((open) => !open)}
        >
          Notes
          {documents.length > 0 && <span className="badge">{documents.length}</span>}
        </button>
      </header>

      {notesOpen && (
        <DocumentPanel
          documents={documents}
          loaded={loaded}
          onAdd={addDocument}
          onDelete={deleteDocument}
          onClose={() => setNotesOpen(false)}
        />
      )}

      {/* Centred while there is nothing to read, moved up once there is. */}
      <div className={result ? "stage answered" : "stage"}>
        <form onSubmit={run}>
          <label className="eyebrow" htmlFor="q">
            {empty
              ? "Add some notes first, then ask away"
              : mode === "ask"
                ? "Ask your notes anything"
                : "Find a passage in your notes"}
          </label>

          <input
            id="q"
            ref={inputRef}
            className="big-input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={
              mode === "ask"
                ? "How do I stop my network memorising?"
                : "dropout and weight decay"
            }
            autoFocus
            disabled={busy}
          />

          <div className="ask-row">
            <button type="submit" className="primary" disabled={!query.trim() || busy}>
              {busy ? "Thinking…" : mode === "ask" ? "Ask" : "Search"}
            </button>
            <span className="enter-hint">
              Press <kbd>Enter</kbd> ↵
            </span>

            <div className="mode-toggle" role="group" aria-label="Mode">
              <button
                type="button"
                className={mode === "ask" ? "on" : undefined}
                aria-pressed={mode === "ask"}
                onClick={() => setMode("ask")}
              >
                Ask
              </button>
              <button
                type="button"
                className={mode === "search" ? "on" : undefined}
                aria-pressed={mode === "search"}
                onClick={() => setMode("search")}
              >
                Search
              </button>
            </div>
          </div>
        </form>

        {/* role="alert" so a failure is spoken, not just drawn. */}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {/* The answer replaces earlier content in place, so it is announced
            politely rather than silently swapped in. */}
        <div aria-live="polite" aria-busy={busy}>
          {result && <ResultPanel result={result} hasDocuments={documents.length > 0} />}
        </div>
      </div>
    </div>
  );
}
