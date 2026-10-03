import json
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4
from app.providers.interfaces import (
    Providers,
    ProviderError,
    Rejected,
    UnsupportedDocument,
)
from app.providers.local.extraction import MAX_UPLOAD
from app.schemas.models import CaseResponse, DocumentType, ReviewRequest
from app.services import memory
from app.services.rules import evaluate, finding

log = logging.getLogger("clearpath")
ACTIVE = {"queued", "processing"}
LEASE_SECONDS = 300
LESSON_CACHE_SECONDS = 30  # Cases are polled; avoid one AgentCore search per poll.
DEMO_USER = "demo-user"  # The single local user; AWS mode uses the login's user ID.


def now():
    return datetime.now(timezone.utc).isoformat()


def stale(job: dict) -> bool:
    """True when an active job's worker crashed or its dispatch was lost.

    AWS has no startup recovery hook, so without this a dead worker would lock
    the case on "processing" forever. A late worker cannot publish afterwards:
    finish_run requires the current run ID and lease owner.
    """
    if job["status"] == "processing":
        return job.get("lease_expires_at", 0) < time.time()
    try:
        queued_at = datetime.fromisoformat(job["updated_at"])
    except (KeyError, TypeError, ValueError):
        return True
    return (datetime.now(timezone.utc) - queued_at).total_seconds() > LEASE_SECONDS


class CaseError(Rejected):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class CaseService:
    def __init__(self, providers: Providers):
        self.p = providers
        self._lesson_cache: dict[str, tuple[float, list[str]]] = {}

    def record(self, case_id: str):
        record = self.p.cases.get(case_id)
        if record is None:
            raise CaseError("Case not found.", 404)
        return record

    def get(self, case_id: str) -> CaseResponse:
        record = self.record(case_id)
        job = record["job"]
        if job and job["status"] in ACTIVE and stale(job):
            # Shown, not stored: the next analyze request starts a fresh run.
            job.update(
                status="interrupted",
                stage="Analysis stopped",
                errors=[
                    "The analysis stopped unexpectedly. No all-clear is available; run the analysis again."
                ],
            )
        reviews = record["reviews"]
        record["checklist"] = [
            {
                "finding_id": f["id"],
                "correction": f["recommended_correction"],
                "reviewer_status": reviews.get(f["id"], {}).get("status", "pending"),
            }
            for f in record["findings"]
            if reviews.get(f["id"], {}).get("status") != "dismissed"
        ]
        if self.p.memory and any(f.get("pattern") for f in record["findings"]):
            try:
                learned = self.p.memory.get()
                for f in record["findings"]:
                    if f.get("pattern"):
                        f["memory"] = memory.history(learned, f["pattern"], case_id)
                        # Only patterns with approved decisions in our own store may
                        # surface AgentCore lessons, so withdrawn lessons stay hidden.
                        if f["memory"]["total"]:
                            f["memory"]["lessons"] = self._lessons(
                                f["pattern"], f["memory"]["pattern_label"]
                            )
            except Exception:
                # Memory is advisory context, not a dependency: the case still loads.
                log.warning("case=%s category=memory_read_failed", case_id)
        return CaseResponse.model_validate(record)

    def authorize(self, case_id: str, user: str) -> None:
        """Only the case owner may use it. Others get 404 so IDs reveal nothing."""
        if self.record(case_id).get("owner", DEMO_USER) != user:
            raise CaseError("Case not found.", 404)

    def create(self, name: str, owner: str = DEMO_USER) -> CaseResponse:
        record = dict(
            id=str(uuid4()),
            owner=owner,
            name=name,
            created_at=now(),
            documents=[],
            job=None,
            findings=[],
            reviews={},
            model_input_preview=[],
        )
        self.p.cases.create(record)
        return self.get(str(record["id"]))

    def register_upload(
        self,
        case_id: str,
        document_type: DocumentType,
        filename: str,
        replace: bool = False,
    ) -> dict:
        self.record(case_id)
        document_id = str(uuid4())
        key = f"{case_id}/{document_id}.pdf"
        document = dict(
            id=document_id,
            case_id=case_id,
            document_type=document_type.value,
            filename=f"{document_type.value}.pdf",
            storage_key=key,
            size=0,
            status="pending_upload",
        )

        def add(record):
            if record["job"] and record["job"]["status"] in ACTIVE:
                raise CaseError("Analysis is running; uploads are locked.", 409)
            existing = next(
                (
                    d
                    for d in record["documents"]
                    if d["document_type"] == document_type.value
                    and d["status"] == "uploaded"
                ),
                None,
            )
            if existing and not replace:
                raise CaseError(
                    "A PDF already exists for this type. Choose Replace PDF.", 409
                )
            if existing:
                document["replaces_document_id"] = existing["id"]
            # Replace any prior pending_upload for the same type.
            record["documents"] = [
                d
                for d in record["documents"]
                if not (
                    d["document_type"] == document_type.value
                    and d["status"] == "pending_upload"
                )
            ]
            record["documents"].append(document)
            if not existing:
                record.update(job=None, findings=[], model_input_preview=[])

        # Signing failure must not create a pending replacement or hide the original.
        presign = self.p.documents.presign_upload(key)
        self.p.cases.update(case_id, add)
        return {"document_id": document_id, **presign}

    def complete_upload(self, case_id: str, document_id: str) -> dict:
        record = self.record(case_id)
        doc = next((d for d in record["documents"] if d["id"] == document_id), None)
        if not doc:
            raise CaseError("Document not found in this case.", 404)
        if doc["status"] == "uploaded":
            return doc
        if doc["status"] != "pending_upload":
            raise CaseError("Document is not awaiting upload completion.", 409)
        size = self.p.documents.confirm_upload(doc["storage_key"])

        def mark_uploaded(record):
            if record["job"] and record["job"]["status"] in ACTIVE:
                raise CaseError("Analysis is running; uploads are locked.", 409)
            current = next(
                (d for d in record["documents"] if d["id"] == document_id), None
            )
            if current is None:
                raise CaseError("Upload was superseded. Upload the PDF again.", 409)
            if current["status"] == "uploaded":
                return
            replacement_id = current.pop("replaces_document_id", None)
            if replacement_id:
                if not any(
                    d["id"] == replacement_id and d["status"] == "uploaded"
                    for d in record["documents"]
                ):
                    raise CaseError(
                        "Source document changed. Upload the PDF again.", 409
                    )
                record["documents"] = [
                    d for d in record["documents"] if d["id"] != replacement_id
                ]
            current["status"] = "uploaded"
            current["size"] = size
            record.update(job=None, findings=[], model_input_preview=[])

        updated = self.p.cases.update(case_id, mark_uploaded)
        return next(d for d in updated["documents"] if d["id"] == document_id)

    def upload(
        self,
        case_id: str,
        document_type: DocumentType,
        content: bytes,
        replace: bool = False,
    ) -> dict:
        self.record(case_id)
        if not content or len(content) > MAX_UPLOAD:
            raise CaseError("PDF must be between 1 byte and 5 MB.", 413)
        if not content.startswith(b"%PDF-"):
            raise CaseError("Only PDF uploads are supported.", 415)
        document_id = str(uuid4())
        key = f"{case_id}/{document_id}.pdf"
        # Do not retain user filenames; they can contain sensitive information.
        document = dict(
            id=document_id,
            case_id=case_id,
            document_type=document_type.value,
            filename=f"{document_type.value}.pdf",
            storage_key=key,
            size=len(content),
            status="uploaded",
        )

        def add(record):
            if record["job"] and record["job"]["status"] in ACTIVE:
                raise CaseError("Analysis is running; uploads are locked.", 409)
            if (
                any(
                    d["document_type"] == document_type.value
                    and d["status"] == "uploaded"
                    for d in record["documents"]
                )
                and not replace
            ):
                raise CaseError(
                    "A PDF already exists for this type. Choose Replace PDF.", 409
                )
            self.p.documents.put(key, content)
            record["documents"] = [
                d
                for d in record["documents"]
                if d["document_type"] != document_type.value
            ]
            record["documents"].append(document)
            record.update(job=None, findings=[], model_input_preview=[])

        self.p.cases.update(case_id, add)
        return document

    def document(self, case_id: str, document_id: str) -> bytes:
        record = self.record(case_id)
        doc = next((d for d in record["documents"] if d["id"] == document_id), None)
        if not doc:
            raise CaseError("Document not found in this case.", 404)
        return self.p.documents.get(doc["storage_key"])

    def analyze(self, case_id: str) -> dict:
        self.record(case_id)
        run_id = str(uuid4())

        def start(record):
            job = record["job"]
            if job and job["status"] in ACTIVE and not stale(job):
                return
            if not record["documents"]:
                raise CaseError("Upload at least one PDF first.")
            if any(d["status"] == "pending_upload" for d in record["documents"]):
                raise CaseError("Complete all pending uploads before analyzing.", 409)
            record.update(findings=[], model_input_preview=[])
            record["job"] = dict(
                id=run_id,
                case_id=case_id,
                status="queued",
                progress=0,
                stage="Queued",
                errors=[],
                created_at=now(),
                updated_at=now(),
            )

        record = self.p.cases.update(case_id, start)
        job = record["job"]
        if job["id"] == run_id:
            try:
                if not self.p.dispatcher:
                    raise ProviderError("dispatcher_unavailable")
                self.p.dispatcher.dispatch(case_id, run_id)
            except Exception:
                self._job(
                    case_id,
                    run_id,
                    status="failed",
                    stage="Dispatch failed",
                    errors=["Job dispatch failed. Start a new analysis."],
                )
                raise CaseError(
                    "Job dispatch failed. Start a new analysis.", 503
                ) from None
        return job

    def review(self, case_id: str, finding_id: str, request: ReviewRequest):
        self.record(case_id)
        decision = dict(finding_id=finding_id, **request.model_dump(), updated_at=now())
        reviewed: dict = {}

        def save(record):
            item = next((f for f in record["findings"] if f["id"] == finding_id), None)
            if item is None:
                raise CaseError("Finding not found in this analysis.", 404)
            record["reviews"][finding_id] = decision
            reviewed.update(item)

        self.p.cases.update(case_id, save)
        self._remember(case_id, reviewed, decision)
        return decision

    # ---- review memory -------------------------------------------------------

    def _remember(self, case_id: str, finding: dict, decision: dict) -> None:
        """Store an APPROVED lesson, or withdraw it. Never fails the review itself.

        Only decisions the reviewer explicitly marks "remember" become lessons
        (see docs/product-direction.md). Saving the same finding again without
        "remember" withdraws this case's lesson. Notes are never stored.
        """
        pattern = finding.get("pattern")
        if not self.p.memory or not pattern:
            return
        try:
            if decision.get("remember"):
                self.p.memory.update(
                    lambda data: memory.record(
                        data,
                        pattern,
                        case_id,
                        decision["status"],
                        decision["updated_at"],
                    )
                )
            else:
                self.p.memory.update(lambda data: memory.forget(data, pattern, case_id))
        except Exception:
            log.warning("case=%s category=memory_write_failed", case_id)
            return
        if decision.get("remember") and self.p.lessons:
            text = memory.lesson_text(
                pattern, decision["status"], finding["policy_version"]
            )
            try:
                self.p.lessons.add(pattern, case_id, text)
                self._lesson_cache.pop(pattern, None)
            except Exception:
                log.warning("case=%s category=lesson_write_failed", case_id)

    def _memory_context(
        self, case_id: str, findings: list[dict]
    ) -> dict[str, list[str]]:
        """Approved lessons per pattern from OTHER cases, to inform explanations.

        Read when the analysis runs. A memory failure only means no lessons."""
        if not self.p.memory:
            return {}
        try:
            learned = self.p.memory.get()
        except Exception:
            log.warning("case=%s category=memory_read_failed", case_id)
            return {}
        context = {}
        for pattern in {f["pattern"] for f in findings if f.get("pattern")}:
            past = memory.history(learned, pattern, case_id)
            if past["hint"]:
                lessons = self._lessons(pattern, past["pattern_label"])
                context[pattern] = [past["hint"], *lessons]
        return context

    def _lessons(self, pattern: str, query: str) -> list[str]:
        """AgentCore lessons for a pattern. Advisory: a failure shows none."""
        if not self.p.lessons:
            return []
        cached = self._lesson_cache.get(pattern)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        try:
            found = self.p.lessons.search(pattern, query)
        except Exception:
            log.warning("category=lesson_read_failed")
            found = []
        self._lesson_cache[pattern] = (time.monotonic() + LESSON_CACHE_SECONDS, found)
        return found

    def memory_summary(self) -> dict:
        if not self.p.memory:
            return dict(enabled=False, patterns=[], total_decisions=0)
        rows = memory.summary(self.p.memory.get())
        return dict(
            enabled=True,
            patterns=rows,
            total_decisions=sum(r["total"] for r in rows),
        )

    def reset_memory(self) -> dict:
        if self.p.memory:
            self.p.memory.update(lambda data: data.update(patterns={}))
        return self.memory_summary()

    def _job(self, case_id, run_id, *, owner=None, **changes) -> bool:
        """Update a run, optionally only while the caller owns its active lease."""
        changed = False

        def change(record):
            nonlocal changed
            # DynamoDB optimistic-lock retries invoke this callback again. Report
            # only whether the latest attempt still owns and updates the lease.
            changed = False
            job = record["job"]
            if not job or job["id"] != run_id:
                return
            if owner is not None and not (
                job["status"] == "processing" and job.get("lease_owner") == owner
            ):
                return
            job.update(**changes, updated_at=now())
            changed = True

        self.p.cases.update(case_id, change)
        return changed

    def process(self, case_id: str, run_id: str) -> None:
        owner = str(uuid4())
        if not self.p.cases.claim_run(case_id, run_id, owner, LEASE_SECONDS):
            return
        try:
            record = self.record(case_id)
            extracted, failures = {}, []
            findings = []
            for doc in record["documents"]:
                if not self.p.cases.renew_run(case_id, run_id, owner, LEASE_SECONDS):
                    log.warning("case=%s category=lease_lost", case_id)
                    return
                try:
                    extracted[doc["id"]] = self.p.extraction.extract(
                        self.p.documents.get(doc["storage_key"])
                    )
                except (UnsupportedDocument, ProviderError):
                    failures.append(
                        "A document could not be extracted within the supported single-page text-PDF scope."
                    )
                    findings.append(
                        finding(
                            case_id,
                            run_id,
                            f"EXTRACTION:{doc['id']}",
                            "review_required",
                            "Extraction is unsupported or failed; this document has not been validated.",
                            "Inspect the source manually or upload a supported text-based single-page PDF.",
                            [
                                {
                                    "document_id": doc["id"],
                                    "page": 1,
                                    "excerpt": "[Text unavailable; manual review required]",
                                    "bounding_box": None,
                                }
                            ],
                        )
                    )
            findings += evaluate(case_id, run_id, record["documents"], extracted)
            if any(f["category"] == "review_required" for f in findings):
                failures.append(
                    "Some fields or documents require manual review; this is not an all-clear."
                )
            if not self._job(
                case_id,
                run_id,
                owner=owner,
                stage="Sample rules and privacy checks",
                progress=65,
            ):
                log.warning("case=%s category=lease_lost", case_id)
                return
            previews = []
            context = self._memory_context(case_id, findings)
            for item in findings:
                if not self.p.cases.renew_run(case_id, run_id, owner, LEASE_SECONDS):
                    log.warning("case=%s category=lease_lost", case_id)
                    return
                payload = {
                    "rule_id": item["rule_id"].split(":")[0],
                    "comparison_result": item["category"],
                    "explanation": item["explanation"],
                    "recommended_correction": item["recommended_correction"],
                    "policy_version": item["policy_version"],
                }
                if context.get(item.get("pattern")):
                    # Advisory context for the explanation only; the finding is unchanged.
                    payload["approved_lessons"] = context[item["pattern"]]
                try:
                    filtered = self.p.privacy.filter(json.dumps(payload), "INPUT")
                    if (
                        filtered.status not in {"masked", "unchanged"}
                        or not filtered.text
                    ):
                        raise ProviderError("input_privacy_unavailable_or_blocked")
                    previews.append(json.loads(filtered.text))
                    explanation = self.p.explanations.explain(filtered.text)
                    output = self.p.privacy.filter(explanation, "OUTPUT")
                    if output.status not in {"masked", "unchanged"} or not output.text:
                        raise ProviderError("output_privacy_unavailable_or_blocked")
                    item["explanation"] = output.text
                except Exception:
                    failures.append(
                        "An explanation was withheld or unavailable. The deterministic finding is preserved."
                    )

            result = dict(
                findings=findings,
                model_input_preview=previews,
                status="partial" if failures else "completed",
                progress=100,
                stage="Review required" if failures else "Analysis complete",
                errors=list(dict.fromkeys(failures)),
            )
            if not self.p.cases.finish_run(case_id, run_id, owner, result):
                log.warning("case=%s category=finish_lost_ownership", case_id)
                return
            log.info("case=%s status=%s", case_id, result["status"])
        except Exception:
            if self._job(
                case_id,
                run_id,
                owner=owner,
                status="failed",
                stage="Analysis failed",
                errors=[
                    "Analysis failed. No all-clear is available; review manually or retry."
                ],
            ):
                log.warning("case=%s category=analysis_failed", case_id)
            else:
                log.warning("case=%s category=failure_lost_ownership", case_id)
