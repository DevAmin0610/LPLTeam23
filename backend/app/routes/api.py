from pathlib import Path
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, Response
from app.config import SAMPLES_DIR
from app.providers.local.extraction import MAX_UPLOAD
from app.schemas.models import (
    CaseResponse,
    CreateCase,
    Document,
    DocumentType,
    Job,
    MemorySummary,
    PresignedUploadResponse,
    ReviewDecision,
    ReviewRequest,
    SamplePacket,
    UploadRequest,
)
from app.services.cases import DEMO_USER, CaseError

router = APIRouter()
SAMPLES = {
    "complete": ("Complete and consistent", "All supported sample fields agree."),
    "missing": ("Missing information", "A transfer application has incomplete fields."),
    "conflicting": (
        "Conflicting details",
        "Identifiers and addresses differ across the packet.",
    ),
    "formatting": (
        "Formatting differences",
        "One form writes the street name with an abbreviation; nothing else differs.",
    ),
}


def sample_path(sample_id: str, kind: DocumentType) -> Path:
    if sample_id not in SAMPLES:
        raise CaseError("Sample not found.", 404)
    path = SAMPLES_DIR / sample_id / f"{kind.value}.pdf"
    if not path.exists():
        raise CaseError("Sample PDFs are missing. Run demo/generate.py.", 503)
    return path


def current_user(request: Request) -> str:
    """The signed-in user. In AWS mode, API Gateway's JWT authorizer (Cognito) has
    already verified the token; the backend only reads its subject claim."""
    if request.app.state.settings.app_mode == "demo":
        return DEMO_USER
    event = request.scope.get("aws.event") or {}
    authorizer = event.get("requestContext", {}).get("authorizer", {})
    user = authorizer.get("jwt", {}).get("claims", {}).get("sub")
    if not user:
        raise CaseError("Sign in required.", 401)
    return user


def case_access(case_id: UUID, request: Request) -> None:
    request.app.state.service.authorize(str(case_id), current_user(request))


OWNER_ONLY = [Depends(case_access)]
SIGNED_IN = [Depends(current_user)]


@router.get("/config")
def config(request: Request):
    mode = request.app.state.settings.app_mode
    return {
        "mode": mode,
        "banner": (
            "AWS mode — document analysis uses AWS providers."
            if mode == "aws"
            else "Demo mode — local extraction and simulated AI explanations."
        ),
        "privacy_notice": "Synthetic data only.",
    }


@router.post("/cases", response_model=CaseResponse, status_code=201)
def create_case(body: CreateCase, request: Request):
    return request.app.state.service.create(body.name, owner=current_user(request))


@router.get("/cases/{case_id}", response_model=CaseResponse, dependencies=OWNER_ONLY)
def get_case(case_id: UUID, request: Request):
    return request.app.state.service.get(str(case_id))


@router.post(
    "/cases/{case_id}/uploads",
    response_model=PresignedUploadResponse,
    status_code=201,
    dependencies=OWNER_ONLY,
)
def request_upload(case_id: UUID, body: UploadRequest, request: Request):
    result = request.app.state.service.register_upload(
        str(case_id), body.document_type, body.filename
    )
    return result


@router.post(
    "/cases/{case_id}/documents/{document_id}/complete",
    response_model=Document,
    dependencies=OWNER_ONLY,
)
def complete_upload(case_id: UUID, document_id: UUID, request: Request):
    return request.app.state.service.complete_upload(str(case_id), str(document_id))


@router.post(
    "/cases/{case_id}/documents",
    response_model=Document,
    status_code=201,
    dependencies=OWNER_ONLY,
)
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


@router.get("/cases/{case_id}/documents/{document_id}", dependencies=OWNER_ONLY)
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


@router.post(
    "/cases/{case_id}/analyze",
    response_model=Job,
    status_code=202,
    dependencies=OWNER_ONLY,
)
def analyze(case_id: UUID, request: Request):
    return request.app.state.service.analyze(str(case_id))


@router.put(
    "/cases/{case_id}/findings/{finding_id}/review",
    response_model=ReviewDecision,
    dependencies=OWNER_ONLY,
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
    # Works in both modes: the API writes the committed synthetic PDFs to
    # storage itself (local disk or S3), so the live demo needs no file picker.
    paths = [(kind, sample_path(sample_id, kind)) for kind in DocumentType]
    service = request.app.state.service
    case = service.create(
        f"Sample — {SAMPLES[sample_id][0]}", owner=current_user(request)
    )
    for kind, path in paths:
        service.upload(case.id, kind, path.read_bytes())
    return service.get(case.id)


@router.get("/memory", response_model=MemorySummary, dependencies=SIGNED_IN)
def memory_summary(request: Request):
    """Approved review lessons: privacy-safe patterns and counts only."""
    return request.app.state.service.memory_summary()


@router.post("/memory/reset", response_model=MemorySummary, dependencies=SIGNED_IN)
def reset_memory(request: Request):
    # For rehearsals. Any signed-in user may reset; there are no admin roles yet.
    return request.app.state.service.reset_memory()