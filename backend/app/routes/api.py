from pathlib import Path
from uuid import UUID
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, Response
from app.config import ROOT
from app.providers.local.extraction import MAX_UPLOAD
from app.schemas.models import (
    CaseResponse,
    CreateCase,
    Document,
    DocumentType,
    Job,
    ReviewDecision,
    ReviewRequest,
    SamplePacket,
)
from app.services.cases import CaseError

router = APIRouter()
SAMPLES = {
    "complete": ("Complete and consistent", "All supported sample fields agree."),
    "missing": ("Missing information", "A transfer application has incomplete fields."),
    "conflicting": (
        "Conflicting details",
        "Identifiers and addresses differ across the packet.",
    ),
}


def sample_path(sample_id: str, kind: DocumentType) -> Path:
    if sample_id not in SAMPLES:
        raise CaseError("Sample not found.", 404)
    path = ROOT / "demo" / sample_id / f"{kind.value}.pdf"
    if not path.exists():
        raise CaseError("Sample PDFs are missing. Run demo/generate.py.", 503)
    return path


@router.get("/config")
def config():
    return {
        "mode": "demo",
        "banner": "Demo mode — local extraction and simulated AI explanations.",
        "privacy_notice": "Synthetic data only. Local masking is a demonstration, not production-grade PII detection.",
    }


@router.post("/cases", response_model=CaseResponse, status_code=201)
def create_case(body: CreateCase, request: Request):
    return request.app.state.service.create(body.name)


@router.get("/cases/{case_id}", response_model=CaseResponse)
def get_case(case_id: UUID, request: Request):
    return request.app.state.service.get(str(case_id))


@router.post("/cases/{case_id}/documents", response_model=Document, status_code=201)
async def upload_document(
    case_id: UUID,
    request: Request,
    document_type: DocumentType = Form(...),
    file: UploadFile = File(...),
):
    try:
        content = await file.read(MAX_UPLOAD + 1)
    finally:
        await file.close()
    # Multipart parsing occurs before this limit: this local starter must not be exposed publicly.
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(
        request.app.state.service.upload, str(case_id), document_type, content
    )


@router.get("/cases/{case_id}/documents/{document_id}")
def document(case_id: UUID, document_id: UUID, request: Request):
    return Response(
        request.app.state.service.document(str(case_id), str(document_id)),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="document.pdf"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/cases/{case_id}/analyze", response_model=Job, status_code=202)
def analyze(case_id: UUID, request: Request):
    return request.app.state.service.analyze(str(case_id))


@router.put(
    "/cases/{case_id}/findings/{finding_id}/review", response_model=ReviewDecision
)
def review(case_id: UUID, finding_id: UUID, body: ReviewRequest, request: Request):
    return request.app.state.service.review(str(case_id), str(finding_id), body)


@router.get("/samples", response_model=list[SamplePacket])
def samples():
    return [
        dict(
            id=key,
            name=name,
            description=description,
            documents=[
                dict(
                    document_type=kind.value,
                    filename=f"{kind.value}.pdf",
                    url=f"/api/samples/{key}/{kind.value}.pdf",
                )
                for kind in DocumentType
            ],
        )
        for key, (name, description) in SAMPLES.items()
    ]


@router.get("/samples/{sample_id}/{document_type}.pdf")
def sample_pdf(sample_id: str, document_type: DocumentType):
    return FileResponse(
        sample_path(sample_id, document_type),
        media_type="application/pdf",
        filename=f"{sample_id}-{document_type.value}.pdf",
    )


@router.post("/samples/{sample_id}/load", response_model=CaseResponse, status_code=201)
def load_sample(sample_id: str, request: Request):
    paths = [(kind, sample_path(sample_id, kind)) for kind in DocumentType]
    service = request.app.state.service
    case = service.create(f"Sample — {SAMPLES[sample_id][0]}")
    for kind, path in paths:
        service.upload(case.id, kind, path.read_bytes())
    return service.get(case.id)
