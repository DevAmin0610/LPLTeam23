"""Replace through the same presigned/completion endpoints used by AWS."""

import pytest
from fastapi.testclient import TestClient
from app.config import SAMPLES_DIR, Settings
from app.main import create_app
from app.providers.interfaces import ProviderError
from app.schemas.models import DocumentType


@pytest.fixture
def client(tmp_path):
    with TestClient(
        create_app(Settings(app_mode="demo", local_data_dir=tmp_path))
    ) as client:
        yield client


def seed(client, kind):
    service = client.app.state.service
    case_id = client.post("/api/cases", json={"name": "Synthetic replacement"}).json()[
        "id"
    ]
    content = (SAMPLES_DIR / "complete" / f"{kind}.pdf").read_bytes()
    original = service.upload(case_id, DocumentType(kind), content)
    return service, case_id, content, original


def sign(service):
    service.p.documents.presign_upload = lambda key: {
        "url": "https://s3.example.test",
        "fields": {"key": key},
        "expires_in": 300,
    }


@pytest.mark.parametrize("kind", [kind.value for kind in DocumentType])
def test_presigned_replacement_retains_original_until_completion(client, kind):
    service, case_id, content, original = seed(client, kind)
    sign(service)
    service.p.cases.update(
        case_id,
        lambda record: record.update(
            reviews={"historical-finding": {"status": "dismissed"}},
            findings=[],
            model_input_preview=[{"old": True}],
        ),
    )
    rejected = client.post(
        f"/api/cases/{case_id}/uploads",
        json={"document_type": kind, "filename": "replacement.pdf"},
    )
    assert rejected.status_code == 409
    response = client.post(
        f"/api/cases/{case_id}/uploads",
        json={"document_type": kind, "filename": "replacement.pdf", "replace": True},
    )
    assert response.status_code == 201
    pending_id = response.json()["document_id"]
    assert service.document(case_id, original["id"]) == content
    pending = next(
        d for d in service.record(case_id)["documents"] if d["id"] == pending_id
    )
    service.p.documents.put(pending["storage_key"], content)
    completed = client.post(f"/api/cases/{case_id}/documents/{pending_id}/complete")
    assert completed.status_code == 200
    record = service.record(case_id)
    assert [d["id"] for d in record["documents"]] == [pending_id]
    assert (
        record["job"] is None
        and record["findings"] == record["model_input_preview"] == []
    )
    assert record["reviews"]["historical-finding"]["status"] == "dismissed"
    assert (
        client.post(f"/api/cases/{case_id}/documents/{pending_id}/complete").status_code
        == 200
    )
    assert (
        client.get(f"/api/cases/{case_id}/documents/{original['id']}").status_code
        == 404
    )


@pytest.mark.parametrize("kind", [kind.value for kind in DocumentType])
def test_local_replacement_and_invalid_upload(client, kind):
    service, case_id, content, original = seed(client, kind)
    response = client.post(
        f"/api/cases/{case_id}/documents",
        data={"document_type": kind, "replace": "true"},
        files={"file": ("wrong.pdf", b"not pdf", "application/pdf")},
    )
    assert response.status_code == 415
    assert service.document(case_id, original["id"]) == content
    response = client.post(
        f"/api/cases/{case_id}/documents",
        data={"document_type": kind, "replace": "true"},
        files={"file": ("replacement.pdf", content, "application/pdf")},
    )
    assert response.status_code == 201
    assert len(service.record(case_id)["documents"]) == 1
    assert response.json()["id"] != original["id"]


def test_failed_presign_and_confirmation_keep_original_and_retry_supersedes_pending(
    client,
):
    service, case_id, content, original = seed(client, "client_profile")

    def fail(*args):
        raise ProviderError("upload_failed")

    service.p.documents.presign_upload = fail
    assert (
        client.post(
            f"/api/cases/{case_id}/uploads",
            json={
                "document_type": "client_profile",
                "filename": "x.pdf",
                "replace": True,
            },
        ).status_code
        == 503
    )
    assert len(service.record(case_id)["documents"]) == 1
    sign(service)
    body = {"document_type": "client_profile", "filename": "x.pdf", "replace": True}
    first = client.post(f"/api/cases/{case_id}/uploads", json=body).json()[
        "document_id"
    ]
    assert (
        client.post(f"/api/cases/{case_id}/documents/{first}/complete").status_code
        == 503
    )
    assert service.document(case_id, original["id"]) == content
    assert client.post(f"/api/cases/{case_id}/analyze").status_code == 409
    second = client.post(f"/api/cases/{case_id}/uploads", json=body).json()[
        "document_id"
    ]
    assert first != second
    assert (
        client.post(f"/api/cases/{case_id}/documents/{first}/complete").status_code
        == 404
    )
    assert len(service.record(case_id)["documents"]) == 2


def test_active_analysis_locks_replacement_registration_and_completion(client):
    service, case_id, content, original = seed(client, "client_profile")
    sign(service)
    pending = service.register_upload(
        case_id, DocumentType.client_profile, "x.pdf", replace=True
    )["document_id"]
    document = next(
        d for d in service.record(case_id)["documents"] if d["id"] == pending
    )
    service.p.documents.put(document["storage_key"], content)
    service.p.cases.update(
        case_id, lambda record: record.update(job={"status": "processing"})
    )
    assert (
        client.post(
            f"/api/cases/{case_id}/uploads",
            json={
                "document_type": "client_profile",
                "filename": "x.pdf",
                "replace": True,
            },
        ).status_code
        == 409
    )
    assert (
        client.post(f"/api/cases/{case_id}/documents/{pending}/complete").status_code
        == 409
    )
    assert service.document(case_id, original["id"]) == content
