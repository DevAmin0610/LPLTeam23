import json
import time
import pytest
from fastapi.testclient import TestClient
from app.config import SAMPLES_DIR, Settings
from app.main import _local_lessons, create_app
from app.providers.interfaces import PrivacyResult


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


def test_agentcore_configuration_requires_memory_and_strategy_ids():
    with pytest.raises(ValueError, match="must be supplied together"):
        Settings(agentcore_memory_id="memory-id").validate_mode()
    with pytest.raises(ValueError, match="must be supplied together"):
        Settings(agentcore_memory_strategy_id="strategy-id").validate_mode()
    whitespace = Settings(agentcore_memory_id=" ", agentcore_memory_strategy_id="\t")
    whitespace.validate_mode()
    assert _local_lessons(whitespace) is None


def test_local_server_refuses_aws_mode(tmp_path):
    """A fully configured AWS mode must not start the local (demo-provider) server."""
    settings = Settings(
        app_mode="aws",
        local_data_dir=tmp_path,
        aws_region="us-east-1",
        bedrock_model_id="model",
        bedrock_guardrail_id="guardrail",
        bedrock_guardrail_version="1",
        s3_document_bucket="bucket",
        dynamodb_cases_table="table",
        worker_lambda_function_name="worker",
    )
    with pytest.raises(ValueError, match="demo only"):
        create_app(settings)


def test_second_worker_cannot_claim_active_lease(client):
    """A second process() call while the first holds the lease must be a no-op."""
    service = client.app.state.service
    case_id = client.post("/api/cases", json={"name": "Lease test"}).json()["id"]
    # Inject a queued job directly so the local dispatcher doesn't run it.
    run_id = "run-lease-test"
    service.p.cases.update(
        case_id,
        lambda r: r.update(
            job=dict(
                id=run_id,
                case_id=case_id,
                status="queued",
                progress=0,
                stage="Queued",
                errors=[],
                created_at="now",
                updated_at="now",
            )
        ),
    )
    # First worker claims the lease.
    assert service.p.cases.claim_run(case_id, run_id, "worker-A", 300)
    # Second worker must not claim it.
    claimed_by_b = service.p.cases.claim_run(case_id, run_id, "worker-B", 300)
    assert not claimed_by_b
    record = service.p.cases.get(case_id)
    assert record["job"]["lease_owner"] == "worker-A"


def test_lease_renewal_prevents_recovery(client):
    service = client.app.state.service
    case_id = client.post("/api/cases", json={"name": "Renewal test"}).json()["id"]
    run_id = "run-renewal-test"
    service.p.cases.update(
        case_id,
        lambda r: r.update(
            job=dict(
                id=run_id,
                case_id=case_id,
                status="queued",
                progress=0,
                stage="Queued",
                errors=[],
                created_at="now",
                updated_at="now",
            )
        ),
    )
    assert service.p.cases.claim_run(case_id, run_id, "worker-A", -1)
    assert service.p.cases.renew_run(case_id, run_id, "worker-A", 300)
    assert not service.p.cases.claim_run(case_id, run_id, "worker-B", 300)


def test_expired_lease_allows_recovery(client):
    """An expired lease must allow a new worker to reclaim the run."""
    service = client.app.state.service
    case_id = client.post("/api/cases", json={"name": "Expiry test"}).json()["id"]
    run_id = "run-expiry-test"
    service.p.cases.update(
        case_id,
        lambda r: r.update(
            job=dict(
                id=run_id,
                case_id=case_id,
                status="queued",
                progress=0,
                stage="Queued",
                errors=[],
                created_at="now",
                updated_at="now",
            )
        ),
    )
    # Claim with a lease that has already expired.
    assert service.p.cases.claim_run(case_id, run_id, "worker-A", -1)
    claimed_by_b = service.p.cases.claim_run(case_id, run_id, "worker-B", 300)
    assert claimed_by_b
    record = service.p.cases.get(case_id)
    assert record["job"]["lease_owner"] == "worker-B"


def test_finish_run_rejects_wrong_owner(client):
    """finish_run must not publish results if the caller no longer owns the lease."""
    service = client.app.state.service
    case_id = client.post("/api/cases", json={"name": "Wrong owner test"}).json()["id"]
    run_id = "run-owner-test"
    service.p.cases.update(
        case_id,
        lambda r: r.update(
            job=dict(
                id=run_id,
                case_id=case_id,
                status="queued",
                progress=0,
                stage="Queued",
                errors=[],
                created_at="now",
                updated_at="now",
            )
        ),
    )
    service.p.cases.claim_run(case_id, run_id, "worker-A", 300)
    result = dict(
        findings=[],
        model_input_preview=[],
        status="completed",
        progress=100,
        stage="Done",
        errors=[],
    )
    published = service.p.cases.finish_run(case_id, run_id, "worker-B", result)
    assert not published
    record = service.p.cases.get(case_id)
    assert record["job"]["status"] == "processing"


def test_stale_worker_cannot_update_reclaimed_run(client):
    service = client.app.state.service
    case_id = client.post("/api/cases", json={"name": "Stale worker test"}).json()["id"]
    run_id = "run-stale-worker-test"
    service.p.cases.update(
        case_id,
        lambda r: r.update(
            job=dict(
                id=run_id,
                case_id=case_id,
                status="queued",
                progress=0,
                stage="Queued",
                errors=[],
                created_at="now",
                updated_at="now",
            )
        ),
    )
    assert service.p.cases.claim_run(case_id, run_id, "worker-A", -1)
    assert service.p.cases.claim_run(case_id, run_id, "worker-B", 300)
    assert not service._job(
        case_id,
        run_id,
        owner="worker-A",
        status="failed",
        stage="Stale failure",
        errors=["stale"],
    )
    job = service.p.cases.get(case_id)["job"]
    assert job["status"] == "processing"
    assert job["lease_owner"] == "worker-B"


def test_job_update_reports_latest_optimistic_lock_attempt():
    from types import SimpleNamespace
    from app.services.cases import CaseService

    class RetryingCases:
        def update(self, case_id, mutate):
            first = {
                "job": {
                    "id": "run-retry",
                    "status": "processing",
                    "lease_owner": "worker-A",
                }
            }
            mutate(first)
            latest = {
                "job": {
                    "id": "run-retry",
                    "status": "processing",
                    "lease_owner": "worker-B",
                }
            }
            mutate(latest)
            return latest

    service = CaseService(SimpleNamespace(cases=RetryingCases()))
    assert not service._job(
        "case-retry",
        "run-retry",
        owner="worker-A",
        status="failed",
    )


def test_presigned_upload_flow(client):
    """register_upload returns a presign response; complete_upload marks the doc uploaded."""
    service = client.app.state.service
    case_id = client.post("/api/cases", json={"name": "Presign test"}).json()["id"]

    # Stub presign_upload so the local storage doesn't raise.
    captured_key = {}

    def fake_presign(key):
        captured_key["key"] = key
        return {
            "url": "https://s3.example.com/upload",
            "fields": {"key": key},
            "expires_in": 300,
        }

    original_presign = service.p.documents.presign_upload
    service.p.documents.presign_upload = fake_presign
    try:
        resp = client.post(
            f"/api/cases/{case_id}/uploads",
            json={"document_type": "client_profile", "filename": "client_profile.pdf"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "document_id" in body
        document_id = body["document_id"]
    finally:
        service.p.documents.presign_upload = original_presign

    # Document should be pending_upload.
    case = client.get(f"/api/cases/{case_id}").json()
    doc = next(d for d in case["documents"] if d["id"] == document_id)
    assert doc["status"] == "pending_upload"

    # Simulate the S3 upload by writing the file directly via the local storage.
    storage_key = next(
        d["storage_key"]
        for d in service.p.cases.get(case_id)["documents"]
        if d["id"] == document_id
    )
    # Use a pre-generated sample PDF so we don't need reportlab in the test.
    sample_pdf = SAMPLES_DIR / "complete" / "client_profile.pdf"
    service.p.documents.put(storage_key, sample_pdf.read_bytes())

    # Complete the upload.
    complete = client.post(f"/api/cases/{case_id}/documents/{document_id}/complete")
    assert complete.status_code == 200
    assert complete.json()["status"] == "uploaded"

    # Analyze must now succeed (no pending_upload docs).
    analyze = client.post(f"/api/cases/{case_id}/analyze")
    assert analyze.status_code == 202


def test_analyze_blocked_by_pending_upload(client):
    """analyze must be rejected while any document is still pending_upload."""
    case_id = client.post("/api/cases", json={"name": "Pending test"}).json()["id"]
    client.post(
        f"/api/cases/{case_id}/uploads",
        json={"document_type": "client_profile", "filename": "client_profile.pdf"},
    )
    resp = client.post(f"/api/cases/{case_id}/analyze")
    assert resp.status_code == 409


def load(client, sample):
    return complete(client, client.post(f"/api/samples/{sample}/load").json()["id"])


def test_stuck_job_can_be_rerun(client):
    """A worker that died mid-run must not lock the case on "processing"."""
    service = client.app.state.service
    case_id = client.post("/api/samples/complete/load").json()["id"]

    def inject(lease_expires_at):
        job = dict(
            id="old-run",
            case_id=case_id,
            status="processing",
            progress=40,
            stage="Extracting PDFs",
            errors=[],
            created_at="now",
            updated_at="now",
            lease_owner="worker-A",
            lease_expires_at=lease_expires_at,
        )
        service.p.cases.update(case_id, lambda r: r.update(job=job))

    # A live lease: no duplicate run is started.
    inject(time.time() + 300)
    assert client.post(f"/api/cases/{case_id}/analyze").json()["id"] == "old-run"
    # An expired lease: shown as interrupted, and a fresh run completes.
    inject(time.time() - 1)
    assert client.get(f"/api/cases/{case_id}").json()["job"]["status"] == "interrupted"
    case = complete(client, case_id)
    assert case["job"]["id"] != "old-run" and case["job"]["status"] == "completed"


def test_one_decision_is_not_called_a_pattern():
    from app.services import memory

    data = {}
    memory.record(data, "ADDRESS_REVIEW:formatting_only", "case-1", "dismissed", "t1")
    hint = memory.history(data, "ADDRESS_REVIEW:formatting_only", "new")["hint"]
    assert "1 of 1" in hint and "not a pattern yet" in hint
    memory.record(data, "ADDRESS_REVIEW:formatting_only", "case-2", "dismissed", "t2")
    hint = memory.history(data, "ADDRESS_REVIEW:formatting_only", "new")["hint"]
    assert "2 of 2" in hint and "Likely a false alarm" in hint


def test_cases_are_private_to_their_owner(client):
    service = client.app.state.service
    mine = client.post("/api/cases", json={"name": "Mine"}).json()["id"]
    theirs = service.create("Someone else's case", owner="another-user").id
    assert client.get(f"/api/cases/{mine}").status_code == 200
    assert client.get(f"/api/cases/{theirs}").status_code == 404
    assert client.post(f"/api/cases/{theirs}/analyze").status_code == 404


def address_finding(case):
    return next(f for f in case["findings"] if f["rule_id"] == "ADDRESS_REVIEW")


def test_address_explanation_matches_pattern(client):
    same = address_finding(load(client, "formatting"))
    moved = address_finding(load(client, "conflicting"))
    assert same["pattern"] == "ADDRESS_REVIEW:formatting_only"
    assert "only in formatting" in same["explanation"]
    assert moved["pattern"] == "ADDRESS_REVIEW:different"
    assert "different locations" in moved["explanation"]
    assert "formatting" not in moved["explanation"]


def test_review_memory_learns_only_approved_decisions(client):
    first = load(client, "formatting")
    finding = address_finding(first)
    assert finding["memory"]["total"] == 0
    review = f"/api/cases/{first['id']}/findings/{finding['id']}/review"

    # A decision is not a lesson unless the reviewer approves it with "remember".
    client.put(review, json={"status": "dismissed"})
    assert client.get("/api/memory").json()["total_decisions"] == 0
    client.put(review, json={"status": "dismissed", "remember": True})
    assert client.get("/api/memory").json()["total_decisions"] == 1

    # The next similar case shows the history but still reports the finding.
    memory = address_finding(load(client, "formatting"))["memory"]
    assert memory["dismissed"] == 1 and "1 of 1" in memory["hint"]
    # A real address difference is a different kind of finding: no history applies.
    assert address_finding(load(client, "conflicting"))["memory"]["total"] == 0

    # Before/after: the approved lesson now informs the next case's explanation,
    # and the explanation provider's input shows it. The finding is unchanged.
    assert "Review memory" not in finding["explanation"]
    after = load(client, "formatting")
    informed = address_finding(after)
    assert (
        "Review memory: Reviewers dismissed this in 1 of 1" in informed["explanation"]
    )
    assert (informed["pattern"], informed["severity"]) == (
        finding["pattern"],
        finding["severity"],
    )
    assert any("approved_lessons" in p for p in after["model_input_preview"])

    # Saving without "remember" withdraws the lesson; reset clears everything.
    client.put(review, json={"status": "dismissed"})
    assert client.get("/api/memory").json()["total_decisions"] == 0
    client.put(review, json={"status": "dismissed", "remember": True})
    assert client.post("/api/memory/reset").json()["total_decisions"] == 0
