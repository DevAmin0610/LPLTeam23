"""Public API contract. Machine findings and reviewer decisions are separate records."""

from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    client_profile = "client_profile"
    transfer_application = "transfer_application"
    account_statement = "account_statement"


class CreateCase(BaseModel):
    name: str = Field(default="Untitled transfer", min_length=1, max_length=100)


class Document(BaseModel):
    id: str
    case_id: str
    document_type: DocumentType
    filename: str
    storage_key: str = Field(exclude=True)
    size: int = 0
    status: Literal["pending_upload", "uploaded"] = "uploaded"


class BoundingBox(BaseModel):
    left: float
    top: float
    width: float
    height: float


class Evidence(BaseModel):
    document_id: str
    page: int = 1
    excerpt: str
    bounding_box: BoundingBox | None = None


class FindingMemory(BaseModel):
    """How reviewers decided this kind of finding in OTHER cases. Advisory only."""

    pattern_label: str
    accepted: int = 0
    dismissed: int = 0
    total: int = 0
    # Set only when past decisions lean clearly one way; never changes the finding.
    hint: str | None = None
    # Lessons consolidated by AgentCore Memory, shown only while approved
    # decisions for this pattern exist. Advisory, untrusted text.
    lessons: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    id: str
    case_id: str
    analysis_run_id: str
    rule_id: str
    # Privacy-safe kind of finding (no values), used to remember reviewer decisions.
    pattern: str | None = None
    policy_version: str
    category: Literal[
        "missing_information",
        "identifier_mismatch",
        "address_difference",
        "review_required",
    ]
    severity: Literal["high", "medium", "low"]
    origin: Literal["deterministic_rule", "model_suggestion"] = "deterministic_rule"
    explanation: str
    recommended_correction: str
    evidence: list[Evidence] = Field(default_factory=list)
    memory: FindingMemory | None = None


class MemoryPattern(BaseModel):
    pattern: str
    label: str
    accepted: int
    dismissed: int
    total: int
    updated_at: str | None = None


class MemorySummary(BaseModel):
    enabled: bool
    patterns: list[MemoryPattern] = Field(default_factory=list)
    total_decisions: int = 0


class ReviewDecision(BaseModel):
    finding_id: str
    status: Literal["accepted", "dismissed"]
    note: str | None = Field(default=None, max_length=1000)
    # True when the reviewer approved this decision as a lesson for similar cases.
    remember: bool = False
    updated_at: str


class ReviewRequest(BaseModel):
    status: Literal["accepted", "dismissed"]
    note: str | None = Field(default=None, max_length=1000)
    # Explicit approval to reuse this decision (pattern + status only, never the
    # note) as advisory context for similar findings in other cases.
    remember: bool = False


class Job(BaseModel):
    id: str
    case_id: str
    status: Literal[
        "queued", "processing", "completed", "partial", "failed", "interrupted"
    ]
    progress: int = 0
    stage: str = "Queued"
    errors: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ChecklistItem(BaseModel):
    finding_id: str
    correction: str
    reviewer_status: Literal["pending", "accepted"]


class CaseResponse(BaseModel):
    id: str
    name: str
    created_at: str
    documents: list[Document] = Field(default_factory=list)
    job: Job | None = None
    findings: list[Finding] = Field(default_factory=list)
    reviews: dict[str, ReviewDecision] = Field(default_factory=dict)
    model_input_preview: list[dict[str, Any]] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)


class UploadRequest(BaseModel):
    document_type: DocumentType
    filename: str = Field(min_length=1, max_length=180)


class PresignedUploadResponse(BaseModel):
    document_id: str
    url: str
    fields: dict[str, str]
    expires_in: int = 300


class SamplePacket(BaseModel):
    id: str
    name: str
    description: str
    documents: list[dict[str, str]]
