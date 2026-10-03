"""Offline synthetic regression metrics for extraction and address classification."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.providers.interfaces import (  # pyright: ignore[reportMissingImports]
    Extraction,
    TextLine,
)
from app.services.rules import (  # pyright: ignore[reportMissingImports]
    POLICY,
    comparison_pattern,
    parse_fields,
)

FIELD_CORPUS = [
    (
        "client_profile",
        [
            "Client Name: Jordan Example",
            "SSN: 987-65-4321",
            "Address: 100 Fictional Drive, Demo City, IL 62704",
        ],
        {"Client Name", "SSN", "Address"},
    ),
    (
        "transfer_application",
        [
            "Account Holder: Jordan Example",
            "Social Security Number: 987-65-4321",
            "Mailing Address: 100 Fictional Dr, Demo City, IL 62704",
            "Source Account Number: XQ-7781-4402",
            "Receiving Account Number: DEST-5000",
        ],
        {"Client Name", "SSN", "Address", "Account Number", "Receiving Account"},
    ),
    (
        "account_statement",
        [
            "Account Holder: Jordan Example",
            "Mailing Address: 100 Fictional Drive, Demo City, IL 62704",
            "Account No.: XQ-7781-4420",
        ],
        {"Client Name", "Address", "Account Number"},
    ),
]

BASE_ADDRESS = "100 Fictional Drive, Demo City, IL 62704"
ADDRESS_CORPUS = [
    ("100 Fictional Dr., Demo City, IL 62704", "formatting_only"),
    ("100 Fictional Drive, Demo City, IL 62707", "postal_code_mismatch"),
    ("100 Fictional Drive, Other City, IL 62704", "city_mismatch"),
    ("100 Fictional Drive, Demo City, NY 62704", "state_mismatch"),
    ("200 Imaginary Road, Demo City, IL 62704", "street_mismatch"),
    ("200 Imaginary Road, Other City, NY 10001", "multiple_components_mismatch"),
]


def exact_label_fields(document_type: str, lines: list[str]) -> set[str]:
    required = set(POLICY["required"][document_type])
    return {
        line.partition(":")[0].strip()
        for line in lines
        if ":" in line and line.partition(":")[0].strip() in required
    }


def main() -> int:
    expected_total = exact_total = alias_total = 0
    for document_type, lines, expected in FIELD_CORPUS:
        expected_total += len(expected)
        exact_total += len(exact_label_fields(document_type, lines) & expected)
        parsed, _, _ = parse_fields(
            document_type,
            Extraction(lines=[TextLine(line) for line in lines]),
        )
        alias_total += len(set(parsed) & expected)

    address_correct = sum(
        comparison_pattern("ADDRESS_REVIEW", "Address", [BASE_ADDRESS, candidate])
        == f"ADDRESS_REVIEW:{expected}"
        for candidate, expected in ADDRESS_CORPUS
    )
    print("Synthetic extraction regression corpus (not production accuracy)")
    print(
        f"  Exact-label baseline field recall: {exact_total}/{expected_total} "
        f"({exact_total / expected_total:.1%})"
    )
    print(
        f"  Alias-aware field recall:         {alias_total}/{expected_total} "
        f"({alias_total / expected_total:.1%})"
    )
    print(
        f"  Address classification accuracy:  {address_correct}/{len(ADDRESS_CORPUS)} "
        f"({address_correct / len(ADDRESS_CORPUS):.1%})"
    )
    return (
        0
        if alias_total == expected_total and address_correct == len(ADDRESS_CORPUS)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
