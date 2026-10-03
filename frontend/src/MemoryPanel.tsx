import type { MemorySummary } from "./types";

function lean(m: { accepted: number; dismissed: number; total: number }) {
  if (!m.total) return "none";
  if (m.dismissed / m.total >= 0.75) return "dismissed";
  if (m.accepted / m.total >= 0.75) return "confirmed";
  return "split";
}

function PatternBar({
  accepted,
  dismissed,
  total,
}: {
  accepted: number;
  dismissed: number;
  total: number;
}) {
  if (!total) return null;
  const acceptedPct = Math.round((accepted / total) * 100);
  const dismissedPct = Math.round((dismissed / total) * 100);
  return (
    <div className="memory-bar" aria-label={`${acceptedPct}% accepted, ${dismissedPct}% dismissed`}>
      <div className="memory-bar-accepted" style={{ width: `${acceptedPct}%` }} />
      <div className="memory-bar-dismissed" style={{ width: `${dismissedPct}%` }} />
    </div>
  );
}

export default function MemoryPanel({
  summary,
  busy,
  onReset,
}: {
  summary: MemorySummary | null;
  busy: boolean;
  onReset: () => void;
}) {
  if (!summary?.enabled) return null;

  return (
    <section className="panel learned" aria-live="polite">
      <div className="learned-head">
        <div>
          <h2>
            What ClearPath has learned{" "}
            <span className="count">{summary.total_decisions}</span>
          </h2>
          <p className="muted">
            Decisions reviewers chose to remember, grouped by kind of finding.
            Patterns and counts only: no names, identifiers or notes. Advisory:
            it never changes a finding, and you still make every call.
          </p>
        </div>
        <button
          disabled={busy || !summary.total_decisions}
          onClick={onReset}
          title="Clear remembered decisions (for rehearsals)"
        >
          Reset memory
        </button>
      </div>

      {summary.patterns.length ? (
        <ul className="learned-list">
          {summary.patterns.map((p) => {
            const kind = lean(p);
            return (
              <li key={p.pattern} className={`memory-${kind}`}>
                <div className="memory-pattern-info">
                  <span className="memory-pattern-label">{p.label}</span>
                  <PatternBar
                    accepted={p.accepted}
                    dismissed={p.dismissed}
                    total={p.total}
                  />
                </div>
                <div className="memory-pattern-stats">
                  <span className="learned-counts">
                    <span className="stat-accepted">{p.accepted} accepted</span>
                    {" · "}
                    <span className="stat-dismissed">{p.dismissed} dismissed</span>
                  </span>
                  <span className="memory-total">{p.total} total</span>
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <p>
          Nothing yet. Tick "Remember this decision" when you accept or dismiss
          a finding.
        </p>
      )}

      {summary.total_decisions > 0 && (
        <p className="muted memory-footer">
          {summary.total_decisions} decision
          {summary.total_decisions !== 1 ? "s" : ""} remembered across{" "}
          {summary.patterns.length} pattern
          {summary.patterns.length !== 1 ? "s" : ""}.
        </p>
      )}
    </section>
  );
}
