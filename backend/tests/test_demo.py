import json
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.providers.interfaces import PrivacyResult
from app.schemas.models import ReviewRequest


@pytest.fixture
def client(tmp_path):
    with TestClient(
        create_app(Settings(app_mode="demo", local_data_dir=tmp_path))
    ) as value:
        yield value


def complete(client, case_id):
    job = client.post(f"/api/cases/{case_id}/analyze")
    assert job.status_code == 202
    for _ in range(200):
        case = client.get(f"/api/cases/{case_id}").json()
        if case["job"]["status"] not in {"queued", "processing"}:
            return case
        time.sleep(0.01)
    pytest.fail("Analysis did not finish")


@pytest.mark.parametrize(
    "packet,expected",
    [
        ("complete", set()),
        (
            "missing",
            {
                "REQUIRED:transfer_application:Address",
                "REQUIRED:transfer_application:Receiving Account",
            },
        ),
        ("conflicting", {"SSN_MATCH", "ACCOUNT_MATCH", "ADDRESS_REVIEW"}),
    ],
)
def test_packets(client, packet, expected):
    response = client.post(f"/api/samples/{packet}/load")
    assert response.status_code == 201
    case = complete(client, response.json()["id"])
    assert case["job"]["status"] == "completed"
    assert {f["rule_id"] for f in case["findings"]} == expected
    sanitized = json.dumps(case["model_input_preview"])
    for value in [
        "000-12-3456",
        "000-98-7654",
        "DEMO-10001234",
        "DEMO-90004321",
        "Fictional Lane",
        "Jordan Example",
    ]:
        assert value not in sanitized
    assert "storage_key" not in json.dumps(case)


def test_review_persistence_and_retry(client):
    case = complete(client, client.post("/api/samples/conflicting/load").json()["id"])
    finding_id = case["findings"][0]["id"]
    response = client.put(
        f"/api/cases/{case['id']}/findings/{finding_id}/review",
        json={"status": "accepted", "note": "Verify with client"},
    )
    assert response.status_code == 200
    client.app.state.service.process(case["id"], case["job"]["id"])
    saved = client.get(f"/api/cases/{case['id']}").json()
    assert saved["reviews"][finding_id]["status"] == "accepted"
    document = saved["documents"][0]
    assert client.get(
        f"/api/cases/{case['id']}/documents/{document['id']}"
    ).content.startswith(b"%PDF-")


def test_privacy_failure_prevents_explanation(client):
    class BrokenPrivacy:
        def filter(self, text, direction):
            return PrivacyResult("error")

    class Spy:
        calls = 0

        def explain(self, text):
            self.calls += 1
            return "Should not run"

    service = client.app.state.service
    service.p.privacy = BrokenPrivacy()
    spy = Spy()
    service.p.explanations = spy
    case = complete(client, client.post("/api/samples/conflicting/load").json()["id"])
    assert spy.calls == 0
    assert case["job"]["status"] == "partial"
    assert len(case["findings"]) == 3


def test_unreadable_is_not_clean(client):
    case_id = client.post("/api/cases", json={"name": "Bad PDF"}).json()["id"]
    response = client.post(
        f"/api/cases/{case_id}/documents",
        data={"document_type": "client_profile"},
        files={"file": ("bad.pdf", b"%PDF-not a document", "application/pdf")},
    )
    assert response.status_code == 201
    case = complete(client, case_id)
    assert case["job"]["status"] == "partial"
    assert any(f["category"] == "review_required" for f in case["findings"])


def test_restart_interrupts_job(tmp_path):
    from app.providers.local.storage import SQLiteCaseStorage

    store = SQLiteCaseStorage(tmp_path)
    store.create({"id": "test", "job": {"status": "processing"}})
    SQLiteCaseStorage(tmp_path).interrupt_pending()
    assert store.get("test")["job"]["status"] == "interrupted"


def test_aws_does_not_fallback():
    with pytest.raises(ValueError, match="AWS configuration missing"):
        Settings(app_mode="aws", aws_region="", bedrock_model_id="").validate_mode()
