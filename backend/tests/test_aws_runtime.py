"""Offline checks that the Lambda entry points start in AWS mode without calling AWS."""

import importlib
import json
import pytest

AWS_ENV = {
    "APP_MODE": "aws",
    "AWS_REGION": "us-east-1",
    "BEDROCK_MODEL_ID": "model",
    "BEDROCK_GUARDRAIL_ID": "guardrail",
    "BEDROCK_GUARDRAIL_VERSION": "1",
    "S3_DOCUMENT_BUCKET": "bucket",
    "DYNAMODB_CASES_TABLE": "table",
    "WORKER_LAMBDA_FUNCTION_NAME": "worker",
}


@pytest.fixture
def aws_env(monkeypatch):
    for key, value in AWS_ENV.items():
        monkeypatch.setenv(key, value)


def http_event(path, method="GET", body=None):
    """Minimal API Gateway HTTP API (v2) event, with no signed-in user."""
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "api.example.com", "content-type": "application/json"},
        "requestContext": {
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "203.0.113.1",
                "userAgent": "test",
            },
            "stage": "$default",
        },
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }


def test_api_lambda_starts_in_aws_mode(aws_env):
    # AWS clients are created lazily, so building the app makes no AWS calls.
    api = importlib.reload(importlib.import_module("app.handlers.api"))
    response = api.handler(http_event("/api/config"), None)
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["mode"] == "aws"


def test_aws_mode_requires_a_signed_in_user(aws_env):
    # Rejected before any storage call, so this needs no AWS access.
    api = importlib.reload(importlib.import_module("app.handlers.api"))
    response = api.handler(http_event("/api/cases", "POST", {"name": "Test"}), None)
    assert response["statusCode"] == 401


def test_current_user_reads_the_verified_token_subject():
    from types import SimpleNamespace
    from app.routes.api import current_user
    from app.services.cases import CaseError

    def request(mode, claims=None):
        event = {"requestContext": {"authorizer": {"jwt": {"claims": claims}}}}
        settings = SimpleNamespace(app_mode=mode)
        return SimpleNamespace(
            scope={"aws.event": event} if claims else {},
            app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
        )

    assert current_user(request("aws", {"sub": "user-123"})) == "user-123"
    assert current_user(request("demo")) == "demo-user"
    with pytest.raises(CaseError, match="Sign in required"):
        current_user(request("aws"))


def test_worker_lambda_rejects_bad_events(aws_env):
    worker = importlib.import_module("app.handlers.worker")
    with pytest.raises(ValueError, match="Invalid analysis event"):
        worker.handler({"case_id": "not-a-uuid"}, None)
