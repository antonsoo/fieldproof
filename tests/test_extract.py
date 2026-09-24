from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fieldproof.document.model import Document, Page
from fieldproof.extract.anthropic_provider import DEFAULT_MODEL, AnthropicExtractor
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


class _FakeMessagesAPI:
    def __init__(self, parsed_output: object, stop_reason: str = "end_turn") -> None:
        self._parsed_output = parsed_output
        self._stop_reason = stop_reason
        self.last_call: dict | None = None

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.last_call = kwargs
        return SimpleNamespace(parsed_output=self._parsed_output, stop_reason=self._stop_reason)


class _FakeAnthropicClient:
    def __init__(self, parsed_output: object, stop_reason: str = "end_turn") -> None:
        self.messages = _FakeMessagesAPI(parsed_output, stop_reason)


def test_anthropic_extractor_uses_structured_output_and_returns_result() -> None:
    invoice = Invoice(
        vendor_name=Evidenced(value="Acme", evidence=["Acme"]),
        invoice_number=Evidenced(value="1", evidence=["1"]),
        issue_date=Evidenced(value="2026-01-01", evidence=["2026-01-01"]),
        total=Evidenced(value=10.0, evidence=["10"]),
    )
    fake_client = _FakeAnthropicClient(parsed_output=invoice)
    extractor = AnthropicExtractor(client=fake_client)  # type: ignore[arg-type]

    doc = Document(
        source="test.pdf",
        pages=[Page(number=1, width=612, height=792, text="Acme owes $10", words=[])],
    )
    result = extractor.extract(doc, Invoice)

    assert result.provider == "anthropic"
    assert result.model == DEFAULT_MODEL
    assert result.data is invoice

    call = fake_client.messages.last_call
    assert call is not None
    assert call["output_format"] is Invoice
    assert "Acme owes $10" in call["messages"][0]["content"]


def test_anthropic_extractor_raises_when_no_parsed_output() -> None:
    fake_client = _FakeAnthropicClient(parsed_output=None, stop_reason="max_tokens")
    extractor = AnthropicExtractor(client=fake_client)  # type: ignore[arg-type]

    with pytest.raises(ExtractionError, match="max_tokens"):
        extractor.extract(_empty_document(), Invoice)
