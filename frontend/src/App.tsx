import { useEffect, useState } from "react";
import { api, errorMessage, safePreview, validatePdf } from "./api";
import {
  completeCognitoLogin,
  getAuthConfigurationError,
  getSession,
  hasAuthCallback,
  logout,
  onSessionExpired,
} from "./auth";
import { DOCUMENT_TYPES, categoryLabel, documentLabel } from "./types";
import type {
  AuthSession,
  DocumentType,
  Evidence,
  FindingMemory,
} from "./types";
import { useWorkspace } from "./useWorkspace";
import LoginScreen from "./LoginScreen";
import PdfViewer from "./PdfViewer";
import MemoryPanel from "./MemoryPanel";
import "./style.css";

export default function App() {
  const [session, setSession] = useState<AuthSession | null>(getSession);
  const [authBusy, setAuthBusy] = useState(hasAuthCallback);
  const [authError, setAuthError] = useState(getAuthConfigurationError() || "");

  useEffect(() => {
    const stopListening = onSessionExpired(() => setSession(null));
    if (hasAuthCallback()) {
      void completeCognitoLogin()
        .then((authenticated) => {
          setSession(authenticated);
          setAuthError("");
        })
        .catch((error: unknown) => {
          setAuthError(
            error instanceof Error
              ? error.message
              : "Sign-in could not complete.",
          );
        })
        .finally(() => setAuthBusy(false));
    }
    return stopListening;
  }, []);

  if (authBusy) {
    return (
      <div className="login-backdrop">
        <div className="login-card" role="status">
          Completing secure sign-in…
        </div>
      </div>
    );
  }

  if (!session) {
    return <LoginScreen onLogin={setSession} initialError={authError} />;
  }

  return <Workspace session={session} onLogout={() => setSession(null)} />;
}

function Workspace({
  session,
  onLogout,
}: {
  session: AuthSession;
  onLogout: () => void;
}) {
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
  const hosted = session.mode === "cognito";
  const showSamples = w.config?.mode === "demo";
  const packet = w.samples.find((s) => s.id === sample);

  function handleLogout() {
    logout();
    onLogout();
  }

  async function downloadSample(path: string, filename: string) {
    setFileError("");
    try {
      const blob = await api.samplePdf(path);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (error) {
      setFileError(errorMessage(error));
    }
  }

  return (
    <>
      <header>
        <a className="brand" href="/" aria-label="ClearPath home">
          <img className="brand-logo" src="/clearpath.png" alt="ClearPath" />
        </a>
        <div className="header-right">
          {!hosted && <span className="pill">HACKATHON STARTER</span>}
          <span className="session-user">{session.username}</span>
          <button className="logout-btn" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </header>
      {!hosted && (
        <div className="banner">
          {w.config?.banner ?? "Connecting to the local API…"}
        </div>
      )}
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
          {!hosted && (
            <div className="disclaimer">
              Independent hackathon prototype.
              <br />
              Not endorsed by LPL Financial. Sample policies only.
            </div>
          )}
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
        <section className={`setup panel ${showSamples ? "" : "setup-single"}`}>
          {showSamples && (
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
                disabled={busy || !packet}
                onClick={() => {
                  setSelected(null);
                  void w.loadSample(sample);
                }}
              >
                {w.busy === "sample" ? "Loading…" : "Load sample case"}
              </button>
              <div className="downloads">
                {packet?.documents.map((document) => (
                  <button
                    className="download-link"
                    type="button"
                    key={document.document_type}
                    onClick={() =>
                      void downloadSample(document.url, document.filename)
                    }
                  >
                    {documentLabel(document.document_type)} ↓
                  </button>
                ))}
              </div>
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setSelected(null);
              void w.createCase(name);
            }}
          >
            <h2>
              {showSamples
                ? "Or create your own"
                : "01 · Create a synthetic review case"}
            </h2>
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
              <p className="muted">
                Uploading for an existing type replaces its PDF after the upload
                succeeds. Run analysis again after replacing a document.
              </p>
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
                {c.documents.some(
                  (d) => d.document_type === kind && d.status === "uploaded",
                )
                  ? "Replace PDF"
                  : "Upload PDF"}
              </button>
              <button
                className="primary"
                type="button"
                disabled={
                  busy ||
                  w.active ||
                  !c.documents.length ||
                  c.documents.some((d) => d.status === "pending_upload")
                }
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
                <PdfViewer
                  caseId={c.id}
                  documents={c.documents.filter((d) => d.status === "uploaded")}
                  evidence={selected}
                  onSelectEvidence={setSelected}
                />
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
            <MemoryPanel
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
        {!hosted && (
          <footer>
            ClearPath · Local-first starter · No regulatory compliance guarantee
            <br />
            Unauthenticated demo. Public deployment requires authentication and
            server-side case-access enforcement.
          </footer>
        )}
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
