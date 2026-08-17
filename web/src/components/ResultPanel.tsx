import type { AskResult, Hit, Result } from "../types";

/**
 * Shows either a ranked list of passages (search) or an answer followed by the
 * passages it was built from (ask).
 *
 * The passages are always visible, never collapsed behind a disclosure. An
 * answer you cannot check against its sources is indistinguishable from one
 * the model invented.
 */
export function ResultPanel({
  result,
  hasDocuments,
}: {
  result: Result;
  hasDocuments: boolean;
}) {
  return (
    <section className="result rise">
      {result.kind === "ask" && (
        <>
          {result.fallbacks.length > 0 && <FallbackNotice result={result} />}
          <p className="answer">{result.answer}</p>
          {result.model && (
            <p className="byline">
              answered by <strong>{result.model}</strong>
            </p>
          )}
          <h2 className="section-label">Grounded on</h2>
        </>
      )}
      {result.kind === "search" && <h2 className="section-label">Matching passages</h2>}

      {result.hits.length === 0 ? (
        // Two different reasons for an empty list, and telling them apart is
        // the difference between "you have not added anything" and "your notes
        // do not cover this".
        <p className="muted">
          {hasDocuments
            ? "Nothing in your notes came close to that."
            : "There are no notes to search yet — add some from the Notes panel."}
        </p>
      ) : (
        <ol className="hits">
          {result.hits.map((hit, index) => (
            <HitItem key={`${hit.document_id}-${index}`} hit={hit} />
          ))}
        </ol>
      )}
    </section>
  );
}

/**
 * Says which model stepped aside and why.
 *
 * Worth showing rather than swapping silently: the answer came from a
 * different model than the one selected, and a reader comparing two answers
 * should know that. 429 is the case this exists for — the Gemini free tier
 * allows twenty generations a day.
 */
function FallbackNotice({ result }: { result: AskResult }) {
  return (
    <div className="fallback rise-sm" role="status">
      <span className="fallback-mark" aria-hidden="true" />
      <span>
        {result.fallbacks.map((attempt) => (
          <span key={attempt.provider} className="fallback-line">
            <strong>{attempt.provider}</strong>{" "}
            {attempt.status === 429 ? "hit its rate limit" : `refused (${attempt.status})`}
          </span>
        ))}
        <span className="fallback-line">
          answered with <strong>{result.model}</strong> instead, from the same passages
        </span>
      </span>
    </div>
  );
}

function HitItem({ hit }: { hit: Hit }) {
  // Cosine similarity, so 1.00 is identical and 0.00 unrelated. Cosine can go
  // negative, hence the clamp before it becomes a width.
  const fraction = Math.max(0, Math.min(1, hit.score));

  return (
    <li>
      <div className="hit-head">
        <span>{hit.title ?? `document ${hit.document_id}`}</span>
        <span className="score">
          {/* The bar restates the number visually, so it is hidden from
              screen readers rather than announced twice. */}
          <span className="score-track" aria-hidden="true">
            <span className="score-fill" style={{ width: `${fraction * 100}%` }} />
          </span>
          <span title="cosine similarity">{hit.score.toFixed(3)}</span>
        </span>
      </div>
      <p>{hit.text}</p>
    </li>
  );
}
