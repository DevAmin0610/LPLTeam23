import { useState } from "react";
import { apiUrl, documentUrl, safePreview, validatePdf } from "./api";
import { DOCUMENT_TYPES, categoryLabel, documentLabel } from "./types";
import type {
  DocumentType,
  Evidence,
  FindingMemory,
  MemorySummary,
} from "./types";
import { useWorkspace } from "./useWorkspace";
import "./style.css";

export default function App() {
  const w = useWorkspace();
  const [sample, setSample] = useState("conflicting");
  const [name, setName] = useState("Synthetic transfer review");
  const [kind, setKind] = useState<DocumentType>("client_profile");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const [selected, setSelected] = useState<Evidence | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [remember, setRemember] = useState<Record<string, boolean>>({});
  const c = w.currentCase;
  const busy = !!w.busy || w.restoring;
  const doc =
    c?.documents.find((d) => d.id === selected?.document_id) ?? c?.documents[0];
  const evidence = doc?.id === selected?.document_id ? selected : null;
  const packet = w.samples.find((s) => s.id === sample);
  return (
    <>
      <header>
        <a className="brand" href="/">
          C<span>ClearPath</span>
        </a>
        <span className="pill">HACKATHON STARTER</span>
      </header>
      <div className="banner">
        {w.config?.banner ?? "Connecting to the local API…"}
      </div>
      <main>
        <div className="intro">
          <div>
            <p className="eyebrow">TRANSFER WORKSPACE</p>
            <h1>A clearer path to review.</h1>
            <p>
              Check a fictional packet. Inspect the evidence. You make the
              decision.
            </p>
          </div>
          <div className="disclaimer">
            Independent hackathon prototype.
            <br />
            Not endorsed by LPL Financial. Sample policies only.
          </div>
        </div>
        <p className="privacy">
          {w.config?.privacy_notice ??
            "Synthetic data only. Do not upload real customer documents."}
        </p>
        {[
          w.configError,
          w.samplesError,
          w.error,
          w.pollError,
          w.storageWarning,
          fileError,
        ]
          .filter(Boolean)
          .map((error, i) => (
            <div role="alert" className="error" key={i}>
              {error}
            </div>
          ))}
        {w.configError && (
          <button onClick={w.retryConfig}>Retry connection</button>
        )}
        {w.notice && (
          <p role="status" className="notice">
            {w.notice}
          </p>
        )}
        <section className="setup panel">
          <div>
            <h2>01 · Start with a packet</h2>
            <label htmlFor="sample">Synthetic sample</label>
            <select
              id="sample"
              value={sample}
              onChange={(e) => setSample(e.target.value)}
            >
              {w.samples.map((s) => (
                <option value={s.id} key={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <p className="muted">{packet?.description}</p>
            <button
              className="primary"
              disabled={busy || !w.config || !packet}
              onClick={() => {
                setSelected(null);
                void w.loadSample(sample);
              }}
            >
              {w.busy === "sample" ? "Loading…" : "Load sample case"}
            </button>
            <div className="downloads">
              {packet?.documents.map((d) => (
                <a href={apiUrl(d.url)} key={d.document_type} download>
                  {documentLabel(d.document_type)} ↓
                </a>
              ))}
            </div>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setSelected(null);
              void w.createCase(name);
            }}
          >
            <h2>Or create your own</h2>
            <label htmlFor="case-name">
              Case name — no personal information
            </label>
            <input
              id="case-name"
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <p className="muted">
              Use one labeled, text-based PDF per document type.
            </p>
            <button disabled={busy || !w.config}>Create case</button>
          </form>
        </section>
        {c ? (
          <>
            <section className="case-bar">
              <div>
                <h2>{c.name}</h2>
                <small>Case ID: {c.id}</small>
              </div>
              <button disabled={busy} onClick={() => void w.refresh()}>
                Refresh
              </button>
            </section>
            <form
              className="upload panel"
              onSubmit={(e) => {
                e.preventDefault();
                if (file) void w.upload(file, kind);
              }}
            >
              <label>
                Document type
                <select
                  value={kind}
                  onChange={(e) => setKind(e.target.value as DocumentType)}
                >
                  {DOCUMENT_TYPES.map((t) => (
                    <option value={t.value} key={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                PDF · maximum 5 MB
                <input
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={(e) => {
                    const next = e.target.files?.[0] ?? null;
                    setFile(next);
                    setFileError(next ? (validatePdf(next) ?? "") : "");
                  }}
                />
              </label>
              <button disabled={busy || w.active || !file || !!fileError}>
                Upload PDF
              </button>
              <button
                className="primary"
                type="button"
                disabled={busy || w.active || !c.documents.length}
                onClick={() => void w.analyze()}
              >
                Analyze packet
              </button>
            </form>
            {c.job && (
              <section className="progress panel" aria-live="polite">
                <div>
                  <strong>{c.job.stage}</strong>
                  <span className="pill">{c.job.status}</span>
                </div>
                <progress max={100} value={c.job.progress} />
                {c.job.errors.map((error, i) => (
                  <p className="error" key={i}>
                    {error}
                  </p>
                ))}
              </section>
            )}
            <div className="review-grid">
              <section className="panel viewer">
                <h2>02 · Source documents</h2>
                <div className="tabs">
                  {c.documents.map((d) => (
                    <button
                      key={d.id}
                      className={doc?.id === d.id ? "selected" : ""}
                      onClick={() =>
                        setSelected({
                          document_id: d.id,
                          page: 1,
                          excerpt: "",
                          bounding_box: null,
                        })
                      }
                    >
                      {documentLabel(d.document_type)}
                    </button>
                  ))}
                </div>
                {doc ? (
                  <>
                    <div className="viewer-meta">
                      <span>
                        Original synthetic document · page {evidence?.page ?? 1}
                      </span>
                      <a
                        href={documentUrl(c.id, doc.id)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open PDF ↗
                      </a>
                    </div>
                    <iframe
                      key={`${doc.id}:${evidence?.page ?? 1}`}
                      title={documentLabel(doc.document_type)}
                      src={`${documentUrl(c.id, doc.id)}#page=${evidence?.page ?? 1}`}
                    />
                    {evidence?.excerpt && (
                      <div className="excerpt">
                        <strong>Sanitized source reference</strong>
                        <p>{evidence.excerpt}</p>
                        <small>
                          Page navigation only. Local extraction does not
                          provide reliable bounding boxes.
                        </small>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="empty">
                    Upload a document to view it here.
                  </div>
                )}
              </section>
              <section className="panel findings">
                <h2>
                  03 · Review findings{" "}
                  <span className="count">{c.findings.length}</span>
                </h2>
                <p className="muted">
                  Accept means you agree with a finding—not that it is fixed.
                </p>
                {!c.findings.length && (
                  <div className="empty">
                    {w.active
                      ? "Reading the packet and checking sample rules…"
                      : c.job?.status === "completed"
                        ? "No issues found by these sample rules. This is not a compliance guarantee."
                        : "Your findings will appear after analysis."}
                  </div>
                )}
                {c.findings.map((f) => {
                  const review = c.reviews[f.id];
                  return (
                    <article className="finding" key={f.id}>
                      <div className="finding-meta">
                        <span className={`severity ${f.severity}`}>
                          {f.severity}
                        </span>
                        <span>{categoryLabel[f.category]}</span>
                        <span>{review?.status ?? "pending"}</span>
                      </div>
                      <h3>
                        {f.memory?.pattern_label ??
                          f.rule_id.replaceAll("_", " ")}
                      </h3>
                      <p>{f.explanation}</p>
                      <p className="correction">{f.recommended_correction}</p>
                      {f.memory && <MemoryNote memory={f.memory} />}
                      <div className="evidence-links">
                        {f.evidence.map((ev, i) => (
                          <button key={i} onClick={() => setSelected(ev)}>
                            ↗{" "}
                            {documentLabel(
                              c.documents.find((d) => d.id === ev.document_id)
                                ?.document_type ?? "client_profile",
                            )}{" "}
                            · p. {ev.page}
                          </button>
                        ))}
                      </div>
                      <small>
                        {f.policy_version} · {f.origin.replaceAll("_", " ")}
                      </small>
                      <label className="note-label">
                        Reviewer note (no sensitive information)
                        <textarea
                          maxLength={1000}
                          value={notes[f.id] ?? review?.note ?? ""}
                          onChange={(e) =>
                            setNotes({ ...notes, [f.id]: e.target.value })
                          }
                        />
                      </label>
                      {f.pattern && (
                        <label className="remember">
                          <input
                            type="checkbox"
                            checked={
                              remember[f.id] ?? review?.remember ?? false
                            }
                            onChange={(e) =>
                              setRemember({
                                ...remember,
                                [f.id]: e.target.checked,
                              })
                            }
                          />
                          <span>
                            Remember this decision for similar findings
                            <small>
                              Saves only the kind of finding and your decision.
                              Never names, numbers or notes.
                            </small>
                          </span>
                        </label>
                      )}
                      <div className="actions">
                        <button
                          className={
                            review?.status === "accepted" ? "primary" : ""
                          }
                          disabled={busy}
                          onClick={() =>
                            void w.saveReview(
                              f.id,
                              "accepted",
                              notes[f.id] ?? review?.note ?? "",
                              remember[f.id] ?? review?.remember ?? false,
                            )
                          }
                        >
                          Accept
                        </button>
                        <button
                          disabled={busy}
                          onClick={() =>
                            void w.saveReview(
                              f.id,
                              "dismissed",
                              notes[f.id] ?? review?.note ?? "",
                              remember[f.id] ?? review?.remember ?? false,
                            )
                          }
                        >
                          Dismiss
                        </button>
                      </div>
                    </article>
                  );
                })}
              </section>
            </div>
            <LearnedPanel
              summary={w.learned}
              busy={busy}
              onReset={() => void w.resetMemory()}
            />
            <div className="bottom-grid">
              <section className="panel">
                <h2>Correction checklist</h2>
                <p className="muted">
                  Pending and accepted findings. Dismissed items are excluded.
                </p>
                {c.checklist.length ? (
                  <ul className="checklist">
                    {c.checklist.map((item) => (
                      <li key={item.finding_id}>
                        <span className="checkbox" aria-hidden="true">
                          □
                        </span>
                        <div>
                          {item.correction}
                          <small>{item.reviewer_status}</small>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>No corrections listed yet.</p>
                )}
              </section>
              <section className="panel">
                <h2>What the explanation provider sees</h2>
                <p className="muted">
                  Sanitized comparison outcomes, not source identifiers. Demo
                  explanations are deterministic templates, not a live model.
                </p>
                <details>
                  <summary>Inspect sanitized model-input preview</summary>
                  <pre>
                    {JSON.stringify(
                      safePreview(c.model_input_preview),
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </section>
            </div>
          </>
        ) : (
          <section className="empty panel">
            {w.restoring
              ? "Restoring your saved case…"
              : "Load a sample above to explore the review workflow."}
          </section>
        )}
        <footer>
          ClearPath · Local-first starter · No regulatory compliance guarantee
          <br />
          Unauthenticated demo. Public deployment requires authentication and
          server-side case-access enforcement.
        </footer>
      </main>
    </>
  );
}

function lean(m: { accepted: number; dismissed: number; total: number }) {
  if (!m.total) return "none";
  if (m.dismissed / m.total >= 0.75) return "dismissed";
  if (m.accepted / m.total >= 0.75) return "confirmed";
  return "split";
}

// Past reviewer decisions on this kind of finding. Advisory: it never changes
// the finding, its severity or its place in the checklist.
function MemoryNote({ memory }: { memory: FindingMemory }) {
  const kind = lean(memory);
  return (
    <div className={`memory memory-${kind}`}>
      <strong>Review memory</strong>
      <p>{memory.hint ?? "No past reviews of this kind of finding yet."}</p>
      {memory.total > 0 && (
        <small>
          {memory.dismissed} dismissed · {memory.accepted} confirmed in other
          cases
        </small>
      )}
    </div>
  );
}

function LearnedPanel({
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
          {summary.patterns.map((p) => (
            <li key={p.pattern} className={`memory-${lean(p)}`}>
              <span>{p.label}</span>
              <span className="learned-counts">
                {p.dismissed} dismissed · {p.accepted} confirmed
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p>
          Nothing yet. Tick “Remember this decision” when you accept or dismiss
          a finding.
        </p>
      )}
    </section>
  );
}