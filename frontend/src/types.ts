export interface AuthSession {
  mode: "demo" | "cognito";
  username: string;
  /** Cognito access token in AWS mode; random local token in demo mode. */
  token: string;
  id_token?: string;
  /** Epoch milliseconds; omitted for the local demo session. */
  expires_at?: number;
  /** ISO timestamp */
  created_at: string;
}

export type DocumentType =
  | "client_profile"
  | "transfer_application"
  | "account_statement";
export type Mode = "demo" | "aws";
export interface Config {
  mode: Mode;
  banner: string;
  privacy_notice: string;
}
export interface CaseDocument {
  id: string;
  case_id: string;
  document_type: DocumentType;
  filename: string;
  size: number;
  status: "uploaded" | "pending_upload";
}
export interface Evidence {
  document_id: string;
  page: number;
  excerpt: string;
  bounding_box: {
    left: number;
    top: number;
    width: number;
    height: number;
  } | null;
}
export type ReviewStatus = "accepted" | "dismissed";
export interface ReviewDecision {
  finding_id: string;
  status: ReviewStatus;
  note: string | null;
  /** True when the reviewer approved this decision as a reusable lesson. */
  remember?: boolean;
  updated_at: string;
}
export interface Finding {
  id: string;
  case_id: string;
  analysis_run_id: string;
  rule_id: string;
  policy_version: string;
  category:
    | "missing_information"
    | "identifier_mismatch"
    | "address_difference"
    | "review_required";
  severity: "high" | "medium" | "low";
  origin: "deterministic_rule" | "model_suggestion";
  explanation: string;
  recommended_correction: string;
  evidence: Evidence[];
  /** Privacy-safe kind of finding (no values); keys review memory. */
  pattern?: string | null;
  /** How reviewers decided this kind of finding in other cases. Advisory only. */
  memory?: FindingMemory | null;
}
export interface FindingMemory {
  pattern_label: string;
  accepted: number;
  dismissed: number;
  total: number;
  hint: string | null;
}
export interface MemoryPattern {
  pattern: string;
  label: string;
  accepted: number;
  dismissed: number;
  total: number;
  updated_at: string | null;
}
export interface MemorySummary {
  enabled: boolean;
  patterns: MemoryPattern[];
  total_decisions: number;
}
export type JobStatus =
  | "queued"
  | "processing"
  | "completed"
  | "partial"
  | "failed"
  | "interrupted";
export interface Job {
  id: string;
  case_id: string;
  status: JobStatus;
  progress: number;
  stage: string;
  errors: string[];
  created_at: string;
  updated_at: string;
}
export interface ChecklistItem {
  finding_id: string;
  correction: string;
  reviewer_status: "pending" | "accepted";
}
export interface CaseResponse {
  id: string;
  name: string;
  created_at: string;
  documents: CaseDocument[];
  job: Job | null;
  findings: Finding[];
  reviews: Record<string, ReviewDecision>;
  model_input_preview: Record<string, unknown>[];
  checklist: ChecklistItem[];
}
export interface SamplePacket {
  id: string;
  name: string;
  description: string;
  documents: { document_type: DocumentType; filename: string; url: string }[];
}
export interface PresignedUploadResponse {
  document_id: string;
  url: string;
  fields: Record<string, string>;
  expires_in: number;
}
export const DOCUMENT_TYPES: {
  value: DocumentType;
  label: string;
  short: string;
}[] = [
  { value: "client_profile", label: "Client profile", short: "Profile" },
  {
    value: "transfer_application",
    label: "Transfer application",
    short: "Application",
  },
  {
    value: "account_statement",
    label: "Account statement",
    short: "Statement",
  },
];
export const documentLabel = (type: DocumentType) =>
  DOCUMENT_TYPES.find((item) => item.value === type)?.label ?? type;
export const isActiveJob = (job: Job | null | undefined) =>
  job?.status === "queued" || job?.status === "processing";
export const categoryLabel: Record<Finding["category"], string> = {
  missing_information: "Missing information",
  identifier_mismatch: "Identifier mismatch",
  address_difference: "Address difference",
  review_required: "Review required",
};
