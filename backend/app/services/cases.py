import json
import logging
from datetime import datetime, timezone
from uuid import uuid4
from app.providers.interfaces import Providers, ProviderError, UnsupportedDocument
from app.providers.local.extraction import MAX_UPLOAD
from app.schemas.models import CaseResponse, DocumentType, ReviewRequest
from app.services.rules import evaluate, finding

log = logging.getLogger("clearpath")
ACTIVE = {"queued", "processing"}


def now():
    return datetime.now(timezone.utc).isoformat()


class CaseError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class CaseService:
    def __init__(self, providers: Providers):
        self.p = providers

    def record(self, case_id: str):
        record = self.p.cases.get(case_id)
        if record is None:
            raise CaseError("Case not found.", 404)
        return record

    def get(self, case_id: str) -> CaseResponse:
        record = self.record(case_id)
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
        return CaseResponse.model_validate(record)

    def create(self, name: str) -> CaseResponse:
        record = dict(
            id=str(uuid4()),
            name=name,
            created_at=now(),
            documents=[],
            job=None,
            findings=[],
            reviews={},
            model_input_preview=[],
        )
        self.p.cases.create(record)
        return self.get(record["id"])

    def upload(self, case_id: str, document_type: DocumentType, content: bytes) -> dict:
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
            if any(
                d["document_type"] == document_type.value for d in record["documents"]
            ):
                raise CaseError(
                    "One document per type is supported. Create a new case to replace the packet.",
                    409,
                )
            self.p.documents.put(key, content)
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
            if record["job"] and record["job"]["status"] in ACTIVE:
                return
            if not record["documents"]:
                raise CaseError("Upload at least one PDF first.")
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

        def save(record):
            if not any(f["id"] == finding_id for f in record["findings"]):
                raise CaseError("Finding not found in this analysis.", 404)
            record["reviews"][finding_id] = decision

        self.p.cases.update(case_id, save)
        return decision

    def _job(self, case_id, run_id, **changes):
        def change(record):
            if record["job"] and record["job"]["id"] == run_id:
                record["job"].update(**changes, updated_at=now())

        self.p.cases.update(case_id, change)

    def process(self, case_id: str, run_id: str) -> None:
        # Atomic claim makes local duplicate deliveries no-ops. AWS leases/recovery
        # must be implemented before enabling AWS composition (see handoff).
        claimed = False

        def claim(record):
            nonlocal claimed
            if (
                record["job"]
                and record["job"]["id"] == run_id
                and record["job"]["status"] == "queued"
            ):
                record["job"].update(
                    status="processing",
                    stage="Extracting PDFs",
                    progress=10,
                    updated_at=now(),
                )
                claimed = True

        self.p.cases.update(case_id, claim)
        if not claimed:
            return
        try:
            record = self.record(case_id)
            extracted, failures = {}, []
            findings = []
            for doc in record["documents"]:
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
            self._job(
                case_id, run_id, stage="Sample rules and privacy checks", progress=65
            )
            previews = []
            for item in findings:
                # Only trusted rule-generated prose enters this allowlisted payload.
                # No identifiers, source document text, names, or addresses are sent.
                payload = {
                    "rule_id": item["rule_id"].split(":")[0],
                    "comparison_result": item["category"],
                    "explanation": item["explanation"],
                    "recommended_correction": item["recommended_correction"],
                    "policy_version": item["policy_version"],
                }
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

            def finish(latest):
                if latest["job"]["id"] != run_id:
                    return
                latest.update(findings=findings, model_input_preview=previews)
                latest["job"].update(
                    status="partial" if failures else "completed",
                    progress=100,
                    stage="Review required" if failures else "Analysis complete",
                    errors=list(dict.fromkeys(failures)),
                    updated_at=now(),
                )
                # Never replace reviews when publishing machine results.

            self.p.cases.update(case_id, finish)
            log.info(
                "case=%s status=%s", case_id, "partial" if failures else "completed"
            )
        except Exception:
            self._job(
                case_id,
                run_id,
                status="failed",
                stage="Analysis failed",
                errors=[
                    "Analysis failed. No all-clear is available; review manually or retry."
                ],
            )
            log.warning("case=%s category=analysis_failed", case_id)
