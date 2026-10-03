"""Deterministic comparisons run on protected values BEFORE privacy filtering."""

import json
import re
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from app.providers.interfaces import Extraction

POLICY = json.loads(
    (Path(__file__).resolve().parents[1] / "policies/sample-v1.json").read_text()
)

# ---- privacy-safe patterns for review memory ---------------------------------
#
# A pattern names the KIND of finding (for example "address differs only by
# abbreviation") so reviewer decisions can be remembered across cases. Patterns
# are fixed strings built from rule IDs, document types and field labels. They
# never contain field values, names, identifiers or document IDs.

_STREET_WORDS = {
    "st": "street",
    "rd": "road",
    "ln": "lane",
    "ave": "avenue",
    "av": "avenue",
    "dr": "drive",
    "blvd": "boulevard",
    "ct": "court",
    "pl": "place",
    "ter": "terrace",
    "hwy": "highway",
    "pkwy": "parkway",
    "cir": "circle",
    "apt": "apartment",
    "ste": "suite",
    "n": "north",
    "s": "south",
    "e": "east",
    "w": "west",
}

PATTERN_LABELS = {
    "ADDRESS_REVIEW:formatting_only": "Address differs only by abbreviations or punctuation",
    "ADDRESS_REVIEW:different": "Address is a different location",
    "SSN_MATCH:transposed_digits": "SSN has two neighboring digits swapped",
    "SSN_MATCH:different": "SSN is a different number",
    "ACCOUNT_MATCH:formatting_only": "Account number differs only by dashes or spaces",
    "ACCOUNT_MATCH:different": "Account number is a different account",
    "EXTRACTION": "Document could not be read",
    "LAYOUT": "Document layout not recognized",
}


def pattern_label(pattern: str) -> str:
    if pattern in PATTERN_LABELS:
        return PATTERN_LABELS[pattern]
    kind, _, rest = pattern.partition(":")
    doc, _, field = rest.partition(":")
    where = doc.replace("_", " ")
    if kind == "REQUIRED" and field:
        return f"{field} missing on the {where}"
    if kind == "UNCERTAIN" and field:
        return f"{field} unreadable on the {where}"
    if kind == "DOCUMENT" and doc:
        return f"{where.capitalize()} not supplied"
    return pattern.replace("_", " ").replace(":", " · ")


def _address_key(value: str) -> str:
    words = re.sub(r"[^\w\s]", " ", value.casefold()).split()
    return " ".join(_STREET_WORDS.get(w, w) for w in words)


def _transposed(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    return (
        len(diff) == 2
        and diff[1] == diff[0] + 1
        and a[diff[0]] == b[diff[1]]
        and a[diff[1]] == b[diff[0]]
    )


def comparison_pattern(rule_id: str, field: str, values: list[str]) -> str:
    """Classify a mismatch on ORIGINAL values; only the label leaves this function."""
    if field == "Address":
        same = len({_address_key(v) for v in values}) == 1
        return f"{rule_id}:{'formatting_only' if same else 'different'}"
    if field == "SSN":
        digits = [re.sub(r"\D", "", v) for v in values]
        unique = sorted(set(digits))
        swapped = len(unique) == 2 and _transposed(*unique)
        return f"{rule_id}:{'transposed_digits' if swapped else 'different'}"
    if field == "Account Number":
        squashed = {re.sub(r"[\s-]", "", v).casefold() for v in values}
        return f"{rule_id}:{'formatting_only' if len(squashed) == 1 else 'different'}"
    return rule_id


def difference_note(pattern: str) -> str:
    """Explain a mismatch from its pattern so the text agrees with the finding label."""
    if pattern.endswith(":formatting_only"):
        return "The values differ only in formatting, such as abbreviations, punctuation or dashes; human review is needed."
    if pattern.endswith(":transposed_digits"):
        return "Two neighboring digits appear swapped, which is often a typo; human review is needed."
    if pattern == "ADDRESS_REVIEW:different":
        return "The addresses point to different locations; human review is needed."
    return "The comparison was performed on original values inside the backend."


def default_pattern(rule_id: str) -> str:
    kind = rule_id.split(":", 1)[0]
    # These rule IDs embed a document ID; the pattern must not.
    return kind if kind in {"EXTRACTION", "LAYOUT"} else rule_id


def finding(
    case_id,
    run_id,
    rule_id,
    category,
    explanation,
    correction,
    evidence=None,
    severity="medium",
    pattern=None,
):
    return {
        "id": str(uuid5(NAMESPACE_URL, f"{case_id}/{run_id}/{rule_id}")),
        "case_id": case_id,
        "analysis_run_id": run_id,
        "rule_id": rule_id,
        "pattern": pattern or default_pattern(rule_id),
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
            pattern = comparison_pattern(
                rule["id"], key, [fields[key] for _, fields in candidates]
            )
            explanation = (
                f"{key} differs between supported documents. {difference_note(pattern)}"
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
                    f"Confirm the correct {key if key.isupper() else key.lower()} with the client and reconcile the packet.",
                    evidence,
                    rule["severity"],
                    pattern,
                )
            )
    return findings
