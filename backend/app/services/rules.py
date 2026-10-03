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

MIN_FIELD_CONFIDENCE = 0.85

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
    "apt": "unit",
    "apartment": "unit",
    "ste": "suite",
    "n": "north",
    "s": "south",
    "e": "east",
    "w": "west",
}

PATTERN_LABELS = {
    "ADDRESS_REVIEW:formatting_only": "Address differs only by abbreviations or punctuation",
    "ADDRESS_REVIEW:postal_code_mismatch": "ZIP or postal code differs between documents",
    "ADDRESS_REVIEW:state_mismatch": "State differs between documents",
    "ADDRESS_REVIEW:city_mismatch": "City differs between documents",
    "ADDRESS_REVIEW:street_mismatch": "Street address differs between documents",
    "ADDRESS_REVIEW:multiple_components_mismatch": "Multiple address components differ",
    "ADDRESS_REVIEW:different": "Address could not be matched component by component",
    "SSN_MATCH:transposed_digits": "SSN has two neighboring digits swapped",
    "SSN_MATCH:different": "SSN is a different number",
    "ACCOUNT_MATCH:formatting_only": "Account number differs only by dashes or spaces",
    "ACCOUNT_MATCH:different": "Account number is a different account",
    "EXTRACTION": "Document could not be read",
    "LAYOUT": "Document layout not recognized",
    "ACCOUNT_TYPE_MATCH": "Account registration type differs between documents",
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


def _label_key(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _field_aliases(document_type: str) -> dict[str, str]:
    aliases = {}
    configured = POLICY.get("aliases", {}).get(document_type, {})
    for canonical in POLICY["required"][document_type] + POLICY.get("optional", {}).get(
        document_type, []
    ):
        for alias in configured.get(canonical, [canonical]):
            key = _label_key(alias)
            previous = aliases.get(key)
            if previous and previous != canonical:
                raise ValueError(f"Ambiguous field alias in policy: {alias}")
            aliases[key] = canonical
        aliases[_label_key(canonical)] = canonical
    return aliases


def parse_fields(
    document_type: str, extraction: Extraction
) -> tuple[dict[str, str], set[str], dict[str, dict[str, float] | None]]:
    """Map extracted labels to canonical policy fields without guessing."""
    aliases = _field_aliases(document_type)
    candidates = [
        (field.label, field.value, field.confidence, field.bounding_box)
        for field in extraction.fields
    ]
    for line in extraction.lines:
        parts = re.split(r"\s*[:=]\s*", line.text, maxsplit=1)
        if len(parts) == 2:
            candidates.append((parts[0], parts[1], line.confidence, line.bounding_box))

    fields: dict[str, str] = {}
    uncertain: set[str] = set()
    boxes: dict[str, dict[str, float] | None] = {}
    for label, value, confidence, box in candidates:
        canonical = aliases.get(_label_key(label))
        if not canonical:
            continue
        value = value.strip()
        if canonical in fields:
            if fields[canonical].casefold() != value.casefold():
                uncertain.add(canonical)
            continue
        if confidence < MIN_FIELD_CONFIDENCE:
            uncertain.add(canonical)
        fields[canonical] = value
        boxes[canonical] = box
    return fields, uncertain, boxes


def _valid_account_number(value: str) -> bool:
    """Accept bounded synthetic identifiers without assuming institution prefixes."""
    compact = re.sub(r"[\s-]", "", value)
    return (
        4 <= len(compact) <= 32
        and compact.isalnum()
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 -]*[A-Za-z0-9]", value) is not None
    )


def _address_key(value: str) -> str:
    words = re.sub(r"[^\w\s]", " ", value.casefold()).split()
    return " ".join(_STREET_WORDS.get(w, w) for w in words)


def _address_components(value: str) -> dict[str, str] | None:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if len(parts) < 3:
        return None
    region = _address_key(parts[-1]).split()
    if len(region) < 2 or not re.fullmatch(r"\d{5}(?:-\d{4})?", region[-1]):
        return None
    return {
        "street": _address_key(parts[0]),
        "city": _address_key(" ".join(parts[1:-1])),
        "state": region[-2],
        "postal_code": region[-1],
    }


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
        if len({_address_key(v) for v in values}) == 1:
            return f"{rule_id}:formatting_only"
        components = [_address_components(value) for value in values]
        if any(component is None for component in components):
            return f"{rule_id}:different"
        complete = [component for component in components if component is not None]
        changed = [
            key
            for key in ("street", "city", "state", "postal_code")
            if len({component[key] for component in complete}) > 1
        ]
        if len(changed) == 1:
            return f"{rule_id}:{changed[0]}_mismatch"
        if changed:
            return f"{rule_id}:multiple_components_mismatch"
        return f"{rule_id}:different"
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
    address_notes = {
        "ADDRESS_REVIEW:postal_code_mismatch": "Only the ZIP or postal code differs; human review is needed.",
        "ADDRESS_REVIEW:state_mismatch": "Only the state differs; human review is needed.",
        "ADDRESS_REVIEW:city_mismatch": "Only the city differs; human review is needed.",
        "ADDRESS_REVIEW:street_mismatch": "Only the street address differs; human review is needed.",
        "ADDRESS_REVIEW:multiple_components_mismatch": "Multiple address components differ; human review is needed.",
        "ADDRESS_REVIEW:different": "The address could not be matched safely by component; human review is needed.",
    }
    if pattern in address_notes:
        return address_notes[pattern]
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
        fields, uncertain, boxes = parse_fields(doc["document_type"], extraction)
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
        parsed[doc["document_type"]] = (doc, fields, uncertain, boxes)
        for key in dict.fromkeys(
            required + POLICY.get("optional", {}).get(doc["document_type"], [])
        ):
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
                and not _valid_account_number(value)
            ):
                uncertain.add(key)
            evidence = [
                {
                    "document_id": doc["id"],
                    "page": 1,
                    "bounding_box": boxes.get(key),
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
            elif not value and key in required:
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
            (doc, fields, boxes)
            for doc, fields, uncertain, boxes in candidates
            if fields.get(key) and key not in uncertain
        ]
        values = [
            re.sub(r"\s+", " ", fields[key]).strip().casefold()
            for _, fields, _ in candidates
        ]
        if key == "Account Type":
            values = [_label_key(value) for value in values]
        if key == "SSN":
            values = [value.replace("-", "") for value in values]
        if len(set(values)) > 1:
            pattern = comparison_pattern(
                rule["id"], key, [fields[key] for _, fields, _ in candidates]
            )
            explanation = (
                f"{key} differs between supported documents. {difference_note(pattern)}"
            )
            evidence = [
                {
                    "document_id": doc["id"],
                    "page": 1,
                    "bounding_box": boxes.get(key),
                    "excerpt": f"{key}: [VALUE WITHHELD]",
                }
                for doc, _, boxes in candidates
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
                    "low" if pattern.endswith(":formatting_only") else rule["severity"],
                    pattern,
                )
            )
    return findings
