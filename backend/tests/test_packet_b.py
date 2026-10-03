"""Regression tests use the uploaded fictional PDFs, not prefilled field dictionaries."""

from pathlib import Path

import pytest
from app.providers.interfaces import ExtractedField, Extraction, TextLine
from app.providers.local.extraction import LocalPDFExtractor
from app.services.rules import evaluate, parse_fields

FIXTURES = Path(__file__).parent / "fixtures" / "packet_b"


def packet():
    documents = [
        {"id": kind, "document_type": kind}
        for kind in ("transfer_application", "client_profile", "account_statement")
    ]
    extracted = {
        doc["id"]: LocalPDFExtractor().extract(
            (FIXTURES / f"packetB_{doc['id']}.pdf").read_bytes()
        )
        for doc in documents
    }
    return documents, extracted


def test_packet_b_real_pdf_fields_and_findings():
    documents, extracted = packet()
    statement, uncertain, _ = parse_fields(
        "account_statement", extracted["account_statement"]
    )
    assert statement["Client Name"] == "Priya R. Nandakumar"
    assert statement["Account Number"] == "MT-2290-6613"
    assert statement["Address"].startswith("88 Harborview Ln")
    assert not uncertain
    application, uncertain, _ = parse_fields(
        "transfer_application", extracted["transfer_application"]
    )
    assert application["Receiving Account"] == "MT-2290-6613"
    assert application["Date of Birth"] == application["Signature Date"] == ""
    assert "Account Number" not in application  # Never alias a destination to a source.
    findings = evaluate("case", "run", documents, extracted)
    assert {f["rule_id"] for f in findings if f["severity"] != "low"} == {
        "REQUIRED:transfer_application:Date of Birth",
        "REQUIRED:transfer_application:Signature Date",
        "ACCOUNT_TYPE_MATCH",
    }
    advisory = next(f for f in findings if f["rule_id"] == "ADDRESS_REVIEW")
    assert advisory["pattern"] == "ADDRESS_REVIEW:formatting_only"
    assert advisory["severity"] == "low"
    mismatch = next(f for f in findings if f["rule_id"] == "ACCOUNT_TYPE_MATCH")
    assert len(mismatch["evidence"]) == 3
    assert mismatch["policy_version"] == "sample-transfer-v2"


def test_packet_b_textract_fields_and_lines_have_same_results():
    documents, extracted = packet()
    structured = {}
    for doc in documents:
        fields, _, _ = parse_fields(doc["document_type"], extracted[doc["id"]])
        structured[doc["id"]] = Extraction(
            lines=extracted[doc["id"]].lines,
            fields=[
                ExtractedField(label, value, confidence=0.99)
                for label, value in fields.items()
            ],
        )
    assert evaluate("case", "run", documents, structured) == evaluate(
        "case", "run", documents, extracted
    )


@pytest.mark.parametrize(
    "replacement, expected", [("Roth IRA", False), ("Traditional IRA", True)]
)
def test_account_type_normalization_preserves_registration_difference(
    replacement, expected
):
    documents, extracted = packet()
    extracted["transfer_application"].lines = [
        TextLine(f"Account Type: {replacement}")
        if line.text.startswith("Account Type:")
        else line
        for line in extracted["transfer_application"].lines
    ]
    findings = evaluate("case", "run", documents, extracted)
    assert any(f["rule_id"] == "ACCOUNT_TYPE_MATCH" for f in findings) is expected


def test_low_confidence_account_type_requires_review_instead_of_confirmed_mismatch():
    documents, extracted = packet()
    extracted["transfer_application"] = Extraction(
        fields=[ExtractedField("Account Type", "Traditional IRA", confidence=0.4)],
        lines=extracted["transfer_application"].lines,
    )
    findings = evaluate("case", "run", documents, extracted)
    assert any(
        f["rule_id"] == "UNCERTAIN:transfer_application:Account Type" for f in findings
    )
    assert not any(f["rule_id"] == "ACCOUNT_TYPE_MATCH" for f in findings)


def test_packet_b_upload_analyze_http_workflow(tmp_path):
    import time
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app

    with TestClient(
        create_app(Settings(app_mode="demo", local_data_dir=tmp_path))
    ) as client:
        case_id = client.post("/api/cases", json={"name": "Synthetic Packet B"}).json()[
            "id"
        ]
        documents, _ = packet()
        for doc in documents:
            path = FIXTURES / f"packetB_{doc['id']}.pdf"
            response = client.post(
                f"/api/cases/{case_id}/documents",
                data={"document_type": doc["document_type"]},
                files={"file": (path.name, path.read_bytes(), "application/pdf")},
            )
            assert response.status_code == 201
        assert client.post(f"/api/cases/{case_id}/analyze").status_code == 202
        for _ in range(200):
            case = client.get(f"/api/cases/{case_id}").json()
            if case["job"]["status"] not in {"queued", "processing"}:
                break
            time.sleep(0.01)
        assert case["job"]["status"] == "partial"
        assert case["job"]["errors"] == [
            "Some fields or documents require manual review; this is not an all-clear."
        ]
        assert {f["rule_id"] for f in case["findings"] if f["severity"] != "low"} == {
            "REQUIRED:transfer_application:Date of Birth",
            "REQUIRED:transfer_application:Signature Date",
            "ACCOUNT_TYPE_MATCH",
        }
        preview = str(case["model_input_preview"])
        assert "Priya" not in preview
        assert "MT-2290-6613" not in preview
        assert "987-65-4188" not in preview
