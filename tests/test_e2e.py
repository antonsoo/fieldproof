"""End-to-end pipeline tests against the committed sample documents
(examples/*.pdf + examples/fixtures/*.json) - the same files the static
Pages demo is built from (see scripts/build_demo_data.py). These pin down
exactly which fields the planted errors are expected to surface as, so a
change to grounding or verification that silently stops catching one of
them fails a test, not just a visual check of the demo.
"""

from __future__ import annotations

import json
from pathlib import Path

from fieldproof.document.loader import load_pdf
from fieldproof.extract.fixture_provider import FixtureExtractor
from fieldproof.schemas import BUILTIN_SCHEMAS
from fieldproof.verify.engine import FieldStatus, verify

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _run(schema_name: str) -> dict:
    doc = load_pdf(EXAMPLES_DIR / f"{schema_name}.pdf")
    schema = BUILTIN_SCHEMAS[schema_name]
    extractor = FixtureExtractor(fixture_path=EXAMPLES_DIR / "fixtures" / f"{schema_name}.json")
    extraction = extractor.extract(doc, schema)
    report = verify(extraction.data, doc)
    return {f.path: f for f in report.fields}


def test_invoice_catches_hallucinated_po_number() -> None:
    fields = _run("invoice")
    assert fields["po_number"].status == FieldStatus.UNSUPPORTED


def test_invoice_catches_total_that_does_not_match_line_items() -> None:
    fields = _run("invoice")
    assert fields["total"].status == FieldStatus.NEEDS_REVIEW
    assert any("2666.93" in r for r in fields["total"].reasons)


def test_invoice_correct_fields_are_verified() -> None:
    fields = _run("invoice")
    for path in ("vendor_name", "invoice_number", "issue_date", "due_date", "payment_terms"):
        assert fields[path].status == FieldStatus.VERIFIED, f"{path}: {fields[path].reasons}"
    for i in range(4):
        assert fields[f"line_items[{i}].amount"].status == FieldStatus.VERIFIED


def test_receipt_catches_misread_date() -> None:
    fields = _run("receipt")
    assert fields["transaction_date"].status == FieldStatus.NEEDS_REVIEW
    assert any("2026-03-14" in r for r in fields["transaction_date"].reasons)


def test_receipt_other_fields_are_verified() -> None:
    fields = _run("receipt")
    for path in ("merchant_name", "subtotal", "tax", "total", "payment_method"):
        assert fields[path].status == FieldStatus.VERIFIED, f"{path}: {fields[path].reasons}"


def test_contract_is_fully_verified_with_no_planted_errors() -> None:
    fields = _run("contract")
    statuses = {path: f.status for path, f in fields.items()}
    assert all(status == FieldStatus.VERIFIED for status in statuses.values()), statuses


def test_all_fixtures_are_valid_json_matching_their_declared_schema() -> None:
    for name, schema in BUILTIN_SCHEMAS.items():
        path = EXAMPLES_DIR / "fixtures" / f"{name}.json"
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        schema.model_validate(raw["data"])
