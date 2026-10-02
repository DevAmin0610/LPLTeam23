import type {
  CaseDocument,
  CaseResponse,
  Config,
  DocumentType,
  Job,
  Mode,
  PresignedUploadResponse,
  ReviewDecision,
  ReviewStatus,
  SamplePacket,
} from "./types";

const configuredBase = (
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
).replace(/\/+$/, "");
export const API_BASE_URL = configuredBase;
export const apiUrl = (path: string) =>
  `${API_BASE_URL}/${path.replace(/^\/+/, "")}`;
const segment = encodeURIComponent;
const casePath = (id: string) => `/api/cases/${segment(id)}`;
export const documentUrl = (caseId: string, documentId: string) =>
  apiUrl(`${casePath(caseId)}/documents/${segment(documentId)}`);

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export const errorMessage = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";

// Only the API's public detail field is eligible for display; never surface raw
// response bodies, storage upload fields, request URLs, or browser network errors.
async function failure(response: Response): Promise<ApiError> {
  let message =
    response.status === 404
      ? "This case or resource could not be found."
      : response.status === 409
        ? "The case is busy. Refresh its status and try again."
        : response.status === 413
          ? "This PDF exceeds the server’s upload limit."
          : `The server could not complete this request (HTTP ${response.status}). Please try again.`;
  try {
    const body: unknown = await response.json();
    if (
      body &&
      typeof body === "object" &&
      "detail" in body &&
      typeof body.detail === "string"
    ) {
      message = body.detail;
    }
  } catch {
    /* Non-JSON errors must not leak proxy or storage response bodies. */
  }
  return new ApiError(message, response.status);
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = 25_000,
): Promise<T> {
  const controller = new AbortController();
  const callerSignal = init.signal;
  const abort = () => controller.abort();
  callerSignal?.addEventListener("abort", abort, { once: true });
  if (callerSignal?.aborted) controller.abort();
  let timedOut = false;
  const timer = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    const response = await fetch(apiUrl(path), {
      ...init,
      signal: controller.signal,
      headers: { Accept: "application/json", ...init.headers },
    });
    if (!response.ok) throw await failure(response);
    try {
      return (await response.json()) as T;
    } catch {
      throw new ApiError(
        "The server returned an unreadable response. Refresh and try again.",
      );
    }
  } catch (error) {
    if (callerSignal?.aborted)
      throw new DOMException("Request cancelled", "AbortError");
    if (timedOut)
      throw new ApiError(
        "The request timed out. Its outcome may be unknown; refresh the case before retrying.",
      );
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      "Cannot reach the API. Check that the backend is running and permits this frontend origin, then retry.",
    );
  } finally {
    window.clearTimeout(timer);
    callerSignal?.removeEventListener("abort", abort);
  }
}
const json = (method: string, body?: unknown): RequestInit => ({
  method,
  ...(body !== undefined
    ? {
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    : {}),
});

export const api = {
  config: (signal?: AbortSignal) => request<Config>("/api/config", { signal }),
  samples: (signal?: AbortSignal) =>
    request<SamplePacket[]>("/api/samples", { signal }),
  createCase: (name: string) =>
    request<CaseResponse>("/api/cases", json("POST", { name })),
  getCase: (id: string, signal?: AbortSignal) =>
    request<CaseResponse>(casePath(id), { signal }),
  loadSample: (id: string) =>
    request<CaseResponse>(
      `/api/samples/${segment(id)}/load`,
      json("POST"),
      90_000,
    ),
  analyze: (id: string) =>
    request<Job>(`${casePath(id)}/analyze`, json("POST")),
  review: (
    caseId: string,
    findingId: string,
    status: ReviewStatus,
    note: string,
  ) =>
    request<ReviewDecision>(
      `${casePath(caseId)}/findings/${segment(findingId)}/review`,
      json("PUT", { status, note: note.trim() || null }),
    ),
  async upload(
    caseId: string,
    file: File,
    documentType: DocumentType,
    mode: Mode,
  ): Promise<CaseDocument> {
    if (mode === "demo") {
      const form = new FormData();
      form.append("file", file);
      form.append("document_type", documentType);
      return request<CaseDocument>(
        `${casePath(caseId)}/documents`,
        { method: "POST", body: form },
        120_000,
      );
    }
    const upload = await request<PresignedUploadResponse>(
      `${casePath(caseId)}/uploads`,
      json("POST", { filename: file.name, document_type: documentType }),
    );
    const form = new FormData();
    for (const [name, value] of Object.entries(upload.fields))
      form.append(name, value);
    // S3 POST requires the file after the signed fields. Never set Content-Type manually.
    form.append("file", file);
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 120_000);
    try {
      const response = await fetch(upload.url, {
        method: "POST",
        body: form,
        signal: controller.signal,
        credentials: "omit",
      });
      if (!response.ok) throw new Error("Storage rejected upload");
    } catch {
      throw new ApiError(
        "The storage upload failed or timed out. Check your connection and the bucket’s CORS configuration, then upload the PDF again. A pending document may remain.",
      );
    } finally {
      window.clearTimeout(timer);
    }
    return request<CaseDocument>(
      `${casePath(caseId)}/documents/${segment(upload.document_id)}/complete`,
      json("POST"),
    );
  },
};

export function validatePdf(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".pdf"))
    return "Choose a PDF document (.pdf).";
  if (file.size === 0) return "This file is empty. Choose a PDF with content.";
  if (file.name.length > 180)
    return "Use a filename of 180 characters or fewer.";
  return null;
}

// Defense in depth for a preview supplied by the backend. The public contract
// contains comparison outcomes, not storage metadata or presigned credentials.
export function safePreview(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(safePreview);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .filter(
          ([key]) =>
            !/(storage.?key|source.?key|s3.?key|bucket|presign|credential|secret|token|signature)/i.test(
              key,
            ),
        )
        .map(([key, item]) => [key, safePreview(item)]),
    );
  }
  return value;
}
