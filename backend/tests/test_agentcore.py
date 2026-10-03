"""AgentCore lessons: request shapes, approval gating, privacy and failure handling."""

import re
import time
from datetime import datetime, timezone

import boto3
import botocore.session
import pytest
from botocore.stub import ANY, Stubber
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers.aws.agentcore import AgentCoreLessons, actor_id

MEMORY_ID = "clearpath-AbCdEfGh12"
LABEL = "Address differs only by abbreviations or punctuation"


@pytest.fixture
def client(tmp_path):
    with TestClient(
        create_app(Settings(app_mode="demo", local_data_dir=tmp_path))
    ) as value:
        yield value


def load(client, sample):
    case_id = client.post(f"/api/samples/{sample}/load").json()["id"]
    client.post(f"/api/cases/{case_id}/analyze")
    for _ in range(200):
        case = client.get(f"/api/cases/{case_id}").json()
        if case["job"]["status"] not in {"queued", "processing"}:
            return case
        time.sleep(0.01)
    pytest.fail("Analysis did not finish")


def address_finding(case):
    return next(f for f in case["findings"] if f["rule_id"] == "ADDRESS_REVIEW")


class FakeLessons:
    def __init__(self, fail=False):
        self.added, self.fail = [], fail

    def add(self, pattern, case_id, text):
        if self.fail:
            raise RuntimeError("AgentCore unavailable")
        self.added.append((pattern, case_id, text))

    def search(self, pattern, query, limit=3):
        if self.fail:
            raise RuntimeError("AgentCore unavailable")
        return [f"Learned: {query}"]


def test_actor_ids_are_valid_for_agentcore():
    model = botocore.session.get_session().get_service_model("bedrock-agentcore")
    rule = model.operation_model("CreateEvent").input_shape.members["actorId"]
    for pattern in [
        "ADDRESS_REVIEW:formatting_only",
        "UNCERTAIN:client_profile:Account Number",
    ]:
        assert re.fullmatch(rule.metadata["pattern"], actor_id(pattern))


def test_requests_match_the_agentcore_api():
    settings = Settings(
        app_mode="demo", aws_region="us-east-1", agentcore_memory_id=MEMORY_ID
    )
    lessons = AgentCoreLessons(settings)
    sdk = boto3.client(
        "bedrock-agentcore",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    lessons._clients["bedrock-agentcore"] = sdk
    case_id = "0b58436b-7c16-4e0d-8c0a-2f8fbe636628"
    when = datetime(2026, 10, 3, tzinfo=timezone.utc)
    payload = [{"conversational": {"role": "USER", "content": {"text": "lesson"}}}]
    with Stubber(sdk) as stub:
        stub.add_response(
            "create_event",
            {
                "event": {
                    "memoryId": MEMORY_ID,
                    "actorId": "UNCERTAIN:client_profile:Account-Number",
                    "sessionId": case_id,
                    "eventId": "0000001759449600000#a1b2c3d4",
                    "eventTimestamp": when,
                    "payload": payload,
                }
            },
            {
                "memoryId": MEMORY_ID,
                "actorId": "UNCERTAIN:client_profile:Account-Number",
                "sessionId": case_id,
                "eventTimestamp": ANY,
                "payload": payload,
            },
        )
        stub.add_response(
            "retrieve_memory_records",
            {
                "memoryRecordSummaries": [
                    {
                        "memoryRecordId": "mem-a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6",
                        "content": {
                            "text": " Abbreviation-only address differences are usually dismissed. "
                        },
                        "memoryStrategyId": "semantic-AbCdEfGh12",
                        "namespaces": ["/lessons/ADDRESS_REVIEW:formatting_only"],
                        "createdAt": when,
                    }
                ]
            },
            {
                "memoryId": MEMORY_ID,
                "namespace": "/lessons/ADDRESS_REVIEW:formatting_only",
                "searchCriteria": {"searchQuery": LABEL, "topK": 3},
            },
        )
        lessons.add("UNCERTAIN:client_profile:Account Number", case_id, "lesson")
        found = lessons.search("ADDRESS_REVIEW:formatting_only", LABEL)
        stub.assert_no_pending_responses()
    assert found == ["Abbreviation-only address differences are usually dismissed."]


def test_lessons_follow_approved_decisions(client):
    fake = FakeLessons()
    client.app.state.service.p.lessons = fake
    first = load(client, "formatting")
    review = f"/api/cases/{first['id']}/findings/{address_finding(first)['id']}/review"

    client.put(
        review,
        json={
            "status": "dismissed",
            "note": "Jordan said Ln is fine",
            "remember": True,
        },
    )
    ((pattern, case_id, text),) = fake.added
    assert (pattern, case_id) == ("ADDRESS_REVIEW:formatting_only", first["id"])
    assert "dismissed" in text and LABEL in text
    assert "Jordan" not in text  # Reviewer notes never leave the app.
    assert address_finding(load(client, "formatting"))["memory"]["lessons"] == [
        f"Learned: {LABEL}"
    ]

    # Withdrawing approval hides lessons, even though AgentCore still holds them.
    client.put(review, json={"status": "dismissed"})
    assert address_finding(load(client, "formatting"))["memory"]["lessons"] == []


def test_agentcore_failures_never_break_reviews(client):
    client.app.state.service.p.lessons = FakeLessons(fail=True)
    first = load(client, "formatting")
    review = f"/api/cases/{first['id']}/findings/{address_finding(first)['id']}/review"
    assert (
        client.put(review, json={"status": "dismissed", "remember": True}).status_code
        == 200
    )
    memory = address_finding(load(client, "formatting"))["memory"]
    assert memory["total"] == 1 and memory["lessons"] == []
