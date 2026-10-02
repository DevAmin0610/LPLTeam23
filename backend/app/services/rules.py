"""Deterministic comparisons run on protected values BEFORE privacy filtering."""

import json
import re
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from app.providers.interfaces import Extraction

POLICY = json.loads(
    (Path(__file__).resolve().parents[1] / "policies/sample-v1.json").read_text()
)


def finding(
    case_id,
    run_id,
    rule_id,
    category,
    explanation,
    correction,
    evidence=None,
    severity="medium",
):
    return {
        "id": str(uuid5(NAMESPACE_URL, f"{case_id}/{run_id}/{rule_id}")),
        "case_id": case_id,
        "analysis_run_id": run_id,
        "rule_id": rule_id,
        "policy_version": POLICY["version"],
        "category": category,
        "severity": severity,
        "origin": "deterministic_rule",
        "explanation": explanation,
        "recommended_correction": correction,
        "evidence": evidence or [],
    }


def evaluate(
    case_id: str, run_id: str, documents: list[dict], extracted: dict[str, Extraction]
):
    findings = []
    parsed = {}
    for doc in documents:
        extraction = extracted.get(doc["id"])
        if extraction is None:
            continue
        required = POLICY["required"][doc["document_type"]]
        fields = {}
        uncertain = set()
        for line in extraction.lines:
            label, separator, value = line.text.partition(":")
            if separator and label.strip() in required:
                key = label.strip()
                if key in fields or line.confidence < 0.95:
                    uncertain.add(key)
                fields[key] = value.strip()
        if not fields:
            findings.append(
                finding(
                    case_id,
                    run_id,
                    f"LAYOUT:{doc['id']}",
                    "review_required",
                    "The document does not contain supported labeled fields.",
                    "Review the source manually or upload a supported synthetic PDF.",
                )
            )
            continue
        parsed[doc["document_type"]] = (doc, fields, uncertain)
        for key in required:
            value = fields.get(key, "")
            if (
                value
                and key == "SSN"
                and not re.fullmatch(r"(?:\d{3}-\d{2}-\d{4}|\d{9})", value)
            ):
                uncertain.add(key)
            if (
                value
                and key in {"Account Number", "Receiving Account"}
                and not re.fullmatch(r"(?:DEMO|RECV)-[A-Z0-9-]{4,24}", value)
            ):
                uncertain.add(key)
            evidence = [
                {
                    "document_id": doc["id"],
                    "page": 1,
                    "bounding_box": None,
                    "excerpt": f"{key}: [VALUE WITHHELD]"
                    if value
                    else f"{key}: [blank or label not found on page]",
                }
            ]
            if key in uncertain:
                findings.append(
                    finding(
                        case_id,
                        run_id,
                        f"UNCERTAIN:{doc['document_type']}:{key}",
                        "review_required",
                        f"{key} could not be read with sufficient certainty.",
                        f"Check {key} in the source document; no confirmed mismatch is asserted.",
                        evidence,
                    )
                )
            elif not value:
                findings.append(
                    finding(
                        case_id,
                        run_id,
                        f"REQUIRED:{doc['document_type']}:{key}",
                        "missing_information",
                        f"{key} is missing from the {doc['document_type'].replace('_', ' ')}.",
                        f"Complete {key} and upload an updated packet.",
                        evidence,
                    )
                )
    supplied = {d["document_type"] for d in documents}
    for kind in POLICY["required"]:
        if kind not in supplied:
            findings.append(
                finding(
                    case_id,
                    run_id,
                    f"DOCUMENT:{kind}",
                    "missing_information",
                    f"The {kind.replace('_', ' ')} is missing.",
                    f"Upload the {kind.replace('_', ' ')}.",
                )
            )
    for rule in POLICY["comparisons"]:
        key = rule["field"]
        candidates = [parsed[kind] for kind in rule["documents"] if kind in parsed]
        candidates = [
            (doc, fields)
            for doc, fields, uncertain in candidates
            if fields.get(key) and key not in uncertain
        ]
        values = [
            re.sub(r"\s+", " ", fields[key]).strip().casefold()
            for _, fields in candidates
        ]
        if key == "SSN":
            values = [value.replace("-", "") for value in values]
        if len(set(values)) > 1:
            explanation = f"{key} differs between supported documents. " + (
                "This may be a formatting difference; human review is needed."
                if key == "Address"
                else "The comparison was performed on original values inside the backend."
            )
            evidence = [
                {
                    "document_id": doc["id"],
                    "page": 1,
                    "bounding_box": None,
                    "excerpt": f"{key}: [VALUE WITHHELD]",
                }
                for doc, _ in candidates
            ]
            findings.append(
                finding(
                    case_id,
                    run_id,
                    rule["id"],
                    rule["category"],
                    explanation,
                    f"Confirm the correct {key.lower()} with the client and reconcile the packet.",
                    evidence,
                    rule["severity"],
                )
            )
    return findings
