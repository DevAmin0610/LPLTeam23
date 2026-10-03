import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, errorMessage } from "./api";
import { isActiveJob } from "./types";
import type {
  CaseResponse,
  Config,
  DocumentType,
  MemorySummary,
  ReviewStatus,
  SamplePacket,
} from "./types";

export const CASE_STORAGE_KEY = "clearpath.case-id.v1";
export const POLL_INTERVAL = 1800;
export const isCaseId = (value: string) =>
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);

export function useWorkspace() {
  const [config, setConfig] = useState<Config | null>(null);
  const [configError, setConfigError] = useState("");
  const [configAttempt, setConfigAttempt] = useState(0);
  const [samples, setSamples] = useState<SamplePacket[]>([]);
  const [samplesError, setSamplesError] = useState("");
  const [samplesLoading, setSamplesLoading] = useState(true);
  const [samplesAttempt, setSamplesAttempt] = useState(0);
  const [currentCase, setCurrentCase] = useState<CaseResponse | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [savedId, setSavedId] = useState("");
  const [storageWarning, setStorageWarning] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef(false);
  const [pollError, setPollError] = useState("");
  const [lastSynced, setLastSynced] = useState<Date | null>(null);
  const [pollAttempt, setPollAttempt] = useState(0);
  const [learned, setLearned] = useState<MemorySummary | null>(null);

  // Memory is context, not a dependency: failures leave the panel empty.
  const refreshLearned = useCallback(async () => {
    try {
      setLearned(await api.memory());
    } catch {
      /* The review workflow works without it. */
    }
  }, []);
  useEffect(() => {
    void refreshLearned();
  }, [refreshLearned]);

  useEffect(() => {
    const controller = new AbortController();
    setConfigError("");
    void api
      .config(controller.signal)
      .then((value) => {
        if (value.mode !== "demo" && value.mode !== "aws")
          throw new Error(
            "The backend returned an unsupported mode. No upload will be attempted.",
          );
        if (!controller.signal.aborted) setConfig(value);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setConfigError(errorMessage(cause));
      });
    return () => controller.abort();
  }, [configAttempt]);

  useEffect(() => {
    if (!config) return;
    if (config.mode !== "demo") {
      setSamples([]);
      setSamplesError("");
      setSamplesLoading(false);
      return;
    }
    const controller = new AbortController();
    setSamplesLoading(true);
    setSamplesError("");
    void api
      .samples(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setSamples(value);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setSamplesError(errorMessage(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setSamplesLoading(false);
      });
    return () => controller.abort();
  }, [config, samplesAttempt]);

  useEffect(() => {
    const controller = new AbortController();
    let id: string | null = null;
    try {
      id = localStorage.getItem(CASE_STORAGE_KEY);
    } catch {
      setStorageWarning(
        "Browser storage is unavailable. Keep your case ID to resume later.",
      );
    }
    if (!id || !isCaseId(id)) {
      setRestoring(false);
      return () => controller.abort();
    }
    setSavedId(id);
    void api
      .getCase(id, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) {
          setCurrentCase(value);
          setLastSynced(new Date());
        }
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setError(
            cause instanceof ApiError && cause.status === 404
              ? "Your saved case is no longer available. Create a case or load a sample to start again."
              : `Could not restore your saved case. ${errorMessage(cause)}`,
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setRestoring(false);
      });
    return () => controller.abort();
  }, []);

  const adoptCase = useCallback((value: CaseResponse) => {
    setCurrentCase(value);
    setSavedId(value.id);
    setLastSynced(new Date());
    setPollError("");
    try {
      localStorage.setItem(CASE_STORAGE_KEY, value.id);
      setStorageWarning("");
    } catch {
      setStorageWarning(
        "This browser could not save your case ID. Keep a copy to resume later.",
      );
    }
  }, []);

  const caseId = currentCase?.id;
  const active = isActiveJob(currentCase?.job);
  useEffect(() => {
    if (!caseId || !active) {
      setPollError("");
      return;
    }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    const poll = async () => {
      try {
        const value = await api.getCase(caseId, controller.signal);
        if (controller.signal.aborted) return;
        setCurrentCase(value);
        setLastSynced(new Date());
        setPollError("");
        failures = 0;
        if (!isActiveJob(value.job)) return;
      } catch (cause) {
        if (controller.signal.aborted) return;
        setPollError(errorMessage(cause));
        failures += 1;
      }
      if (!controller.signal.aborted)
        timer = setTimeout(
          () => {
            void poll();
          },
          Math.min(POLL_INTERVAL * 2 ** failures, 15_000),
        );
    };
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [caseId, active, pollAttempt]);

  const run = async (key: string, action: () => Promise<void>) => {
    if (busyRef.current) return false;
    busyRef.current = true;
    setBusy(key);
    setError("");
    setNotice("");
    try {
      await action();
      return true;
    } catch (cause) {
      setError(errorMessage(cause));
      return false;
    } finally {
      busyRef.current = false;
      setBusy(null);
    }
  };

  const startAnalysis = async (value: CaseResponse) => {
    try {
      const job = await api.analyze(value.id);
      setCurrentCase({
        ...value,
        job,
        findings: [],
        reviews: {},
        checklist: [],
        model_input_preview: [],
      });
      setPollAttempt((attempt) => attempt + 1);
      setNotice(
        "Analysis started. You can leave this page and resume with your case ID.",
      );
    } catch (cause) {
      // A timed-out POST may still have started a run. Reconcile rather than
      // implying that it was rolled back or displaying stale previous results.
      try {
        adoptCase(await api.getCase(value.id));
      } catch {
        /* Keep the resumable case and original error. */
      }
      throw cause;
    }
  };

  return {
    config,
    configError,
    retryConfig: () => setConfigAttempt((value) => value + 1),
    samples,
    samplesError,
    samplesLoading,
    retrySamples: () => setSamplesAttempt((value) => value + 1),
    currentCase,
    restoring,
    savedId,
    storageWarning,
    error,
    notice,
    busy,
    active,
    pollError,
    lastSynced,
    learned,
    resetMemory: () =>
      run("memory", async () => {
        setLearned(await api.resetMemory());
        setNotice("Review memory cleared.");
      }),
    clearError: () => setError(""),
    createCase: (name: string) =>
      run("create", async () => {
        adoptCase(await api.createCase(name.trim()));
        setNotice("Case created. Add your PDFs to begin.");
      }),
    resumeCase: (id: string) =>
      run("resume", async () => {
        if (!isCaseId(id.trim()))
          throw new Error("Enter a valid case ID in UUID format.");
        adoptCase(await api.getCase(id.trim()));
        setNotice(
          "Case restored. Your documents and saved decisions are ready.",
        );
      }),
    loadSample: (id: string) =>
      run("sample", async () => {
        if (!config)
          throw new Error("Connect to the API before loading a sample packet.");
        const value = await api.loadSample(id);
        adoptCase(value);
        await startAnalysis(value);
      }),
    analyze: () =>
      run("analyze", async () => {
        if (currentCase) await startAnalysis(currentCase);
      }),
    upload: (file: File, documentType: DocumentType) =>
      run("upload", async () => {
        if (!currentCase || !config) return;
        try {
          const document = await api.upload(
            currentCase.id,
            file,
            documentType,
            config.mode,
            currentCase.documents.some(
              (item) =>
                item.document_type === documentType &&
                item.status === "uploaded",
            ),
          );
          setCurrentCase((value) =>
            value?.id === currentCase.id
              ? {
                  ...value,
                  documents: [
                    ...value.documents.filter(
                      (item) => item.document_type !== document.document_type,
                    ),
                    document,
                  ],
                }
              : value,
          );
          setNotice(
            "PDF saved. Run analysis again to check the updated packet.",
          );
        } finally {
          // Also fetch after failure: AWS may have registered a pending document.
          try {
            adoptCase(await api.getCase(currentCase.id));
          } catch {
            setPollError(
              "The document list could not be refreshed. Refresh the case before retrying the upload.",
            );
          }
        }
      }),
    refresh: () =>
      run("refresh", async () => {
        if (currentCase) adoptCase(await api.getCase(currentCase.id));
        setPollAttempt((attempt) => attempt + 1);
      }),
    saveReview: (
      findingId: string,
      status: ReviewStatus,
      note: string,
      remember = false,
    ) =>
      run(`review:${findingId}`, async () => {
        if (!currentCase) return;
        const review = await api.review(
          currentCase.id,
          findingId,
          status,
          note,
          remember,
        );
        setCurrentCase((value) => {
          if (!value || value.id !== currentCase.id) return value;
          const reviews = { ...value.reviews, [findingId]: review };
          return {
            ...value,
            reviews,
            checklist: value.findings
              .filter((finding) => reviews[finding.id]?.status !== "dismissed")
              .map((finding) => ({
                finding_id: finding.id,
                correction: finding.recommended_correction,
                reviewer_status:
                  reviews[finding.id]?.status === "accepted"
                    ? "accepted"
                    : "pending",
              })),
          };
        });
        setNotice(
          `Review ${status} and saved${remember ? " and remembered for similar findings" : ""}. Accepting a finding does not mark its correction complete.`,
        );
        await refreshLearned();
      }),
  };
}
export type Workspace = ReturnType<typeof useWorkspace>;
