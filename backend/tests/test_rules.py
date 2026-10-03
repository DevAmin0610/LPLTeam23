from app.providers.aws.adapters import _textract_fields
from app.providers.interfaces import ExtractedField, Extraction, TextLine
from app.services.rules import comparison_pattern, evaluate, parse_fields


def extraction(*lines: str) -> Extraction:
    return Extraction(lines=[TextLine(line) for line in lines])


def packet_findings(overrides: dict[str, tuple[str, ...]] | None = None):
    lines = {
        "client_profile": (
            "Client Name: Jordan Example",
            "SSN: 987-65-4321",
            "Address: 100 Fictional Drive, Demo City, IL 62704",
        ),
        "transfer_application": (
            "Account Holder: Jordan Example",
            "Social Security Number: 987-65-4321",
            "Mailing Address: 100 Fictional Dr, Demo City, IL 62704",
            "Source Account Number: XQ-7781-4402",
            "Receiving Account Number: DEST-5000",
        ),
        "account_statement": (
            "Account Holder: Jordan Example",
            "Mailing Address: 100 Fictional Drive, Demo City, IL 62704",
            "Account No.: XQ-7781-4420",
        ),
    }
    lines.update(overrides or {})
    documents = [
        {"id": kind, "document_type": kind}
        for kind in ("client_profile", "transfer_application", "account_statement")
    ]
    extracted = {kind: extraction(*values) for kind, values in lines.items()}
    return evaluate("case", "run", documents, extracted)


def test_aliases_and_generic_account_numbers_enable_mismatch_comparison():
    findings = packet_findings()

    assert [finding["rule_id"] for finding in findings] == [
        "ACCOUNT_MATCH",
        "ADDRESS_REVIEW",
    ]
    assert findings[0]["pattern"] == "ACCOUNT_MATCH:different"
    assert findings[1]["pattern"] == "ADDRESS_REVIEW:formatting_only"
    assert all(not finding["rule_id"].startswith("UNCERTAIN") for finding in findings)
    assert all(not finding["rule_id"].startswith("REQUIRED") for finding in findings)


def test_receiving_account_alias_does_not_fill_source_account_number():
    parsed, uncertain, _ = parse_fields(
        "transfer_application",
        extraction("Receiving Account Number: DEST-5000"),
    )

    assert parsed == {"Receiving Account": "DEST-5000"}
    assert uncertain == set()


def test_structured_fields_take_precedence_over_line_fallback():
    box = {"left": 0.1, "top": 0.2, "width": 0.3, "height": 0.04}
    parsed, uncertain, boxes = parse_fields(
        "account_statement",
        Extraction(
            lines=[TextLine("Client Name: Jordan Example", confidence=0.1)],
            fields=[
                ExtractedField(
                    "Account Holder",
                    "Jordan Example",
                    confidence=0.99,
                    bounding_box=box,
                )
            ],
        ),
    )

    assert parsed == {"Client Name": "Jordan Example"}
    assert uncertain == set()
    assert boxes == {"Client Name": box}


def test_text_lines_fill_fields_missing_from_partial_structured_extraction():
    parsed, uncertain, _ = parse_fields(
        "account_statement",
        Extraction(
            lines=[
                TextLine("Mailing Address: 100 Fictional Drive, Demo City, IL 62704")
            ],
            fields=[
                ExtractedField("Account Holder", "Jordan Example", confidence=0.99)
            ],
        ),
    )

    assert parsed == {
        "Client Name": "Jordan Example",
        "Address": "100 Fictional Drive, Demo City, IL 62704",
    }
    assert uncertain == set()


def test_zip_mismatch_is_classified_without_treating_abbreviation_as_location_change():
    transfer = (
        "Account Holder: Jordan Example",
        "Social Security Number: 987-65-4321",
        "Mailing Address: 100 Fictional Dr, Demo City, IL 62707",
        "Source Account Number: XQ-7781-4420",
        "Receiving Account Number: DEST-5000",
    )
    findings = packet_findings({"transfer_application": transfer})
    address = next(
        finding for finding in findings if finding["rule_id"] == "ADDRESS_REVIEW"
    )

    assert address["pattern"] == "ADDRESS_REVIEW:postal_code_mismatch"
    assert "ZIP or postal code" in address["explanation"]
    assert "different locations" not in address["explanation"]


def test_address_component_patterns():
    base = "100 Fictional Drive, Demo City, IL 62704"
    assert (
        comparison_pattern(
            "ADDRESS_REVIEW",
            "Address",
            [base, "100 Fictional Dr., Demo City, IL 62704"],
        )
        == "ADDRESS_REVIEW:formatting_only"
    )
    assert (
        comparison_pattern(
            "ADDRESS_REVIEW",
            "Address",
            [base, "100 Fictional Drive, Demo City, IL 62707"],
        )
        == "ADDRESS_REVIEW:postal_code_mismatch"
    )
    assert (
        comparison_pattern(
            "ADDRESS_REVIEW",
            "Address",
            [base, "100 Fictional Drive, Other City, IL 62704"],
        )
        == "ADDRESS_REVIEW:city_mismatch"
    )
    assert (
        comparison_pattern(
            "ADDRESS_REVIEW",
            "Address",
            [base, "200 Imaginary Road, Demo City, IL 62704"],
        )
        == "ADDRESS_REVIEW:street_mismatch"
    )
    assert (
        comparison_pattern(
            "ADDRESS_REVIEW",
            "Address",
            [base, "200 Imaginary Road, Other City, NY 10001"],
        )
        == "ADDRESS_REVIEW:multiple_components_mismatch"
    )


def test_textract_form_blocks_become_structured_fields():
    box = {"Left": 0.4, "Top": 0.2, "Width": 0.2, "Height": 0.03}
    response = {
        "Blocks": [
            {
                "Id": "key",
                "BlockType": "KEY_VALUE_SET",
                "EntityTypes": ["KEY"],
                "Confidence": 98.0,
                "Relationships": [
                    {"Type": "CHILD", "Ids": ["key-word-1", "key-word-2"]},
                    {"Type": "VALUE", "Ids": ["value"]},
                ],
            },
            {"Id": "key-word-1", "BlockType": "WORD", "Text": "Account"},
            {"Id": "key-word-2", "BlockType": "WORD", "Text": "Holder"},
            {
                "Id": "value",
                "BlockType": "KEY_VALUE_SET",
                "EntityTypes": ["VALUE"],
                "Confidence": 96.0,
                "Geometry": {"BoundingBox": box},
                "Relationships": [{"Type": "CHILD", "Ids": ["value-word"]}],
            },
            {"Id": "value-word", "BlockType": "WORD", "Text": "Jordan Example"},
        ]
    }

    assert _textract_fields(response) == [
        ExtractedField(
            label="Account Holder",
            value="Jordan Example",
            confidence=0.96,
            bounding_box={
                "left": 0.4,
                "top": 0.2,
                "width": 0.2,
                "height": 0.03,
            },
        )
    ]
