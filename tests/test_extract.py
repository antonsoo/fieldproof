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
        (b"\x80\x81 not text", "fixture.json is not UTF-8 text"),
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


@pytest.mark.parametrize(
    ("text", "pointer"),
    [
        ('{"data":{"total":{"value":900,"value":100}}}', "/data/total/value"),
        ('{"data":{"total":{"value":900,"val\\u0075e":100}}}', "/data/total/value"),
        ('{"data":{"line_items":[{"amount":1,"amount":2}]}}', "/data/line_items/0/amount"),
        ('{"data":{"a/b~c":1,"a/b~c":2}}', "/data/a~1b~0c"),
        ('{"data":{"total":1},"data":{"total":2}}', "/data"),
    ],
)
def test_duplicate_claims_are_not_replaced_by_the_last_member(text: str, pointer: str) -> None:
    from fieldproof.extract.base import read_extraction_json

    with pytest.raises(ExtractionError) as caught:
        read_extraction_json(text, "claims.json")
    assert "claims.json" in str(caught.value)
    assert f"duplicate JSON member at {pointer!r}" in str(caught.value)


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_nonfinite_json_numbers_are_explicit_input_errors(number: str) -> None:
    from fieldproof.extract.base import read_extraction_json

    with pytest.raises(ExtractionError, match="non-finite JSON number at '/data/total/value'"):
        read_extraction_json('{"data":{"total":{"value":' + number + "}}}", "claims.json")


@pytest.mark.parametrize("text", ['{"data":{"value":"\\ud800"}}', '{"\\udfff":1}'])
def test_escaped_lone_surrogates_cannot_reach_saved_or_http_reports(text: str) -> None:
    from fieldproof.extract.base import read_extraction_json

    with pytest.raises(ExtractionError, match="invalid Unicode"):
        read_extraction_json(text, "claims.json")


def test_valid_surrogate_pairs_and_repeated_names_in_separate_objects_are_allowed() -> None:
    from fieldproof.extract.base import read_extraction_json

    assert read_extraction_json(
        '{"first":{"value":"\\ud83d\\ude00"},"second":{"value":"ok"}}', "claims.json"
    ) == {"first": {"value": "😀"}, "second": {"value": "ok"}}


@pytest.mark.parametrize("location", ["root", "row", "wrapper"])
def test_schema_validation_cannot_discard_unrecognized_claims(location: str) -> None:
    from fieldproof.extract.base import validate_data

    data = _fixture_payload()["data"]
    if location == "root":
        data["bank_account"] = {"value": "UNSUPPORTED", "evidence": []}
        path = "bank_account"
    elif location == "row":
        data["line_items"] = [{
            "description": {"value": "Widget"}, "amount": {"value": 10},
            "discount": {"value": 900, "evidence": []},
        }]
        path = "line_items.0.discount"
    else:
        data["total"]["original_value"] = 900
        path = "total.original_value"
    with pytest.raises(ExtractionError) as caught:
        validate_data(data, Invoice, "claims.json")
    assert f"{path}: Extra inputs are not permitted" in str(caught.value)


def test_per_call_extra_policy_preserves_custom_aliases_defaults_and_model_configuration() -> None:
    from pydantic import BaseModel, ConfigDict, Field

    from fieldproof.extract.base import validate_data

    class Person(BaseModel):
        model_config = ConfigDict(extra="allow")
        name: Evidenced[str] = Field(alias="printed_name")
        country: Evidenced[str] | None = None

    class Form(BaseModel):
        people: list[Person]

    clean = {"people": [{"printed_name": {"value": "Jane", "evidence": ["Jane"]}}]}
    validated = validate_data(clean, Form, "form.json")
    assert validated.people[0].name.value == "Jane"
    assert validated.people[0].country is None
    assert Person.model_config["extra"] == "allow"
    damaged = {"people": [{**clean["people"][0], "approval": {"value": True}}]}
    with pytest.raises(ExtractionError, match="people.0.approval: Extra inputs are not permitted"):
        validate_data(damaged, Form, "form.json")
    assert "approval" in Person.model_validate(damaged["people"][0]).model_extra


@pytest.mark.parametrize(
    "encode",
    [
        lambda text: b"\xef\xbb\xbf" + text.encode("utf-8"),
        lambda text: b"\xff\xfe" + text.encode("utf-16-le"),
        lambda text: b"\xfe\xff" + text.encode("utf-16-be"),
    ],
    ids=["utf-8 with a byte-order mark", "utf-16 little-endian", "utf-16 big-endian"],
)
def test_json_saved_by_windows_tools_is_read(encode) -> None:  # type: ignore[no-untyped-def]
    # Notepad's "UTF-8 with BOM" and PowerShell's `>` (UTF-16) both put a mark first, which
    # was refused as "Unexpected UTF-8 BOM" or "not UTF-8 text".
    from fieldproof.extract.base import read_extraction_json

    expected = {"vendor": "Müller & Søn", "total": 12.5}
    text = '{"vendor": "Müller & Søn", "total": 12.5}'
    assert read_extraction_json(encode(text), "result.json") == expected
