import { useState } from "react";

import type { DocumentRow } from "../types";

interface Props {
  documents: DocumentRow[];
  loaded: boolean;
  onAdd: (title: string, text: string) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  onClose: () => void;
}

/**
 * Kept out of the way in a sheet that opens from the top bar, so the question
 * stays the only thing on screen until you go looking for your notes.
 */
export function DocumentPanel({ documents, loaded, onAdd, onDelete, onClose }: Props) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  // Removing a document also drops its embeddings, and the text is not kept
  // anywhere else — so the button asks once before doing it.
  const [confirmId, setConfirmId] = useState<number | null>(null);

  const canSubmit = title.trim() !== "" && text.trim() !== "" && !busy;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;

    setBusy(true);
    try {
      await onAdd(title.trim(), text.trim());
      setTitle("");
      setText("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="sheet">
      <div className="sheet-inner">
        <div className="sheet-head">
          <h2>Your notes</h2>
          <button type="button" className="link" onClick={onClose}>
            close
          </button>
        </div>

        <form onSubmit={submit} className="field">
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Title, e.g. Lecture 3 — Training"
            aria-label="Note title"
            disabled={busy}
          />
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Paste the notes here…"
            aria-label="Note text"
            rows={5}
            disabled={busy}
          />
          <div>
            <button type="submit" className="primary" disabled={!canSubmit}>
              {busy ? "Embedding…" : "Add notes"}
            </button>
          </div>
        </form>

        {/* Nothing is claimed about the list until the first fetch has landed,
            so "nothing added yet" cannot flash on a page that has notes. */}
        {!loaded ? (
          <p className="muted">Loading…</p>
        ) : documents.length === 0 ? (
          <p className="muted">Nothing added yet.</p>
        ) : (
          <ul className="doc-list">
            {documents.map((doc) => (
              <li key={doc.id}>
                <span>
                  <strong>{doc.title}</strong>
                  <span className="muted"> · {doc.chunk_count} chunks</span>
                </span>

                {confirmId === doc.id ? (
                  <span className="confirm">
                    <button
                      type="button"
                      className="link danger"
                      onClick={() => {
                        setConfirmId(null);
                        void onDelete(doc.id);
                      }}
                    >
                      really remove
                    </button>
                    <button
                      type="button"
                      className="link"
                      onClick={() => setConfirmId(null)}
                    >
                      cancel
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    className="link"
                    onClick={() => setConfirmId(doc.id)}
                  >
                    remove
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
