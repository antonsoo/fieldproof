from __future__ import annotations

import json
from pathlib import Path

import pytest

from fieldproof.document.model import Document, Page
from fieldproof.extract.base import ExtractionError, ExtractionResult
from fieldproof.extract.fixture_provider import FixtureExtractor
from fieldproof.schemas import Evidenced, Invoice


def _empty_document() -> Document:
    return Document(
        source="test.pdf", pages=[Page(number=1, width=612, height=792, text="", words=[])]
    )


def _fixture_payload() -> dict:
    return {
        "schema": "Invoice",
        "provider": "fixture",
        "model": "fixture-v1",
        "data": {
            "vendor_name": {"value": "Acme Corp", "evidence": ["Acme Corp"], "page": 1},
            "invoice_number": {"value": "INV-1", "evidence": ["INV-1"], "page": 1},
            "issue_date": {"value": "2026-01-01", "evidence": ["2026-01-01"], "page": 1},
            "total": {"value": 10.0, "evidence": ["10.00"], "page": 1},
            "line_items": [],
        },
    }


def test_fixture_extractor_loads_and_validates(tmp_path: Path) -> None:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(_fixture_payload()), encoding="utf-8")

    result = FixtureExtractor(fixture_path=path).extract(_empty_document(), Invoice)

    assert result.provider == "fixture"
    assert isinstance(result.data, Invoice)
    assert result.data.vendor_name.value == "Acme Corp"


def test_extraction_result_round_trips_through_dict() -> None:
    invoice = Invoice(
        vendor_name=Evidenced(value="Acme", evidence=["Acme"]),
        invoice_number=Evidenced(value="1", evidence=["1"]),
        issue_date=Evidenced(value="2026-01-01", evidence=["2026-01-01"]),
        total=Evidenced(value=10.0, evidence=["10"]),
    )
    result = ExtractionResult(schema_name="Invoice", data=invoice, provider="fixture", model="m")
    round_tripped = ExtractionResult.from_dict(result.to_dict(), Invoice)
    assert round_tripped.data.vendor_name.value == "Acme"
    assert round_tripped.provider == "fixture"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"{ not json", r"fixture\.json is not valid JSON \(line 1, column 3"),
        (b"[1, 2]", "fixture.json must hold a JSON object, not list"),
        (b"\xff\xfe", "fixture.json is not UTF-8 text"),
        (b'{"data": {"vendor_name": 5}}', "does not match the Invoice schema: vendor_name: "),
        (b'{"data": []}', "does not match the Invoice schema: data: "),
    ],
)
def test_fixture_that_cannot_be_used_says_why(tmp_path: Path, content: bytes, message: str) -> None:
    path = tmp_path / "fixture.json"
    path.write_bytes(content)
    with pytest.raises(ExtractionError, match=message):
        FixtureExtractor(fixture_path=path).extract(_empty_document(), Invoice)


def test_schema_mismatch_lists_the_first_problems_and_counts_the_rest(tmp_path: Path) -> None:
    path = tmp_path / "fixture.json"
    path.write_text('{"data": {}}')
    with pytest.raises(ExtractionError) as caught:
        FixtureExtractor(fixture_path=path).extract(_empty_document(), Invoice)
    message = str(caught.value)
    assert message.startswith("fixture.json does not match the Invoice schema: vendor_name: Field")
    assert message.endswith("(and 1 more)")
    assert "\n" not in message


def test_result_without_data_is_an_extraction_error() -> None:
    with pytest.raises(ExtractionError, match='result.json has no "data" object'):
        ExtractionResult.from_dict({"schema": "invoice"}, Invoice, source="result.json")
