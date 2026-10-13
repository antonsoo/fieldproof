"""An unrelated quote cannot supply verification rules for arbitrary objects."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum, IntEnum, StrEnum
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, create_model

from fieldproof.document import load_pdf
from fieldproof.extract.base import validate_data
from fieldproof.schemas import Evidenced, EvidencedDate, EvidencedText
from fieldproof.verify import verify


class Details(BaseModel):
    account: str


class Account(Enum):
    UNKNOWN = "UNSUPPORTED"


class TextChoice(StrEnum):
    EXAMPLE = "Example Works"


class NumberChoice(IntEnum):
    THIRTEEN = 13


@pytest.fixture(scope="module")
def document():
    return load_pdf(Path(__file__).resolve().parents[1] / "studies/claim-types/claims.pdf")


@pytest.mark.parametrize(
    ("annotation", "value", "runtime_type"),
    [
        (dict[str, str], {"account": "UNSUPPORTED"}, "dict"),
        (list[str], ["UNSUPPORTED"], "list"),
        (tuple[str, ...], ["UNSUPPORTED"], "tuple"),
        (set[str], ["UNSUPPORTED"], "set"),
        (str | None, None, "NoneType"),
        (Decimal, "999.99", "Decimal"),
        (date, "2026-05-01", "date"),
        (datetime, "2026-05-01T12:00:00", "datetime"),
        (bytes, "UNSUPPORTED", "bytes"),
        (Details, {"account": "UNSUPPORTED"}, "Details"),
        (Account, "UNSUPPORTED", "Account"),
        (Any, {"account": "UNSUPPORTED"}, "dict"),
    ],
)
def test_validated_custom_models_cannot_verify_unsupported_value_types(
    document, annotation, value, runtime_type,
):
    schema = create_model("Claim", account=(Evidenced[annotation], ...))
    data = validate_data(
        {"account": {"value": value, "evidence": ["Example Works"]}}, schema, "claim.json",
    )
    original = data.model_dump_json()
    with pytest.raises(ValueError) as error:
        verify(data, document)
    assert f"claim at 'account' has unsupported value type {runtime_type}" in str(error.value)
    assert data.model_dump_json() == original


@pytest.mark.parametrize("quotes", [[], ["not on this page"], ["10.00"], ["Example Works"]])
def test_claim_kind_error_does_not_depend_on_quote_availability(document, quotes):
    class Claim(BaseModel):
        account: Evidenced[str | None]

    with pytest.raises(ValueError, match="claim at 'account' has unsupported value type NoneType"):
        verify(Claim(account=Evidenced[str | None](value=None, evidence=quotes)), document)


def test_error_has_exact_nested_path_and_precedes_any_grounding(document, monkeypatch):
    class Row(BaseModel):
        description: Evidenced[dict[str, str]]
        amount: Evidenced[float]

    class Form(BaseModel):
        valid: Evidenced[str]
        groups: dict[str, tuple[Row, ...]]

    data = Form.model_validate({
        "valid": {"value": "Example Works", "evidence": ["Example Works"]},
        "groups": {'x"].items[0]': [{
            "description": {"value": {"account": "UNSUPPORTED"}, "evidence": ["Alpha"]},
            "amount": {"value": 10, "evidence": ["10.00"]},
        }]},
    })
    # A false-green object must neither generate a partial report nor provide
    # a row-location hint that disambiguates the repeated amount on its line.
    def unexpected_grounding(*args, **kwargs):
        pytest.fail("grounding started before validating every claim value")

    monkeypatch.setattr("fieldproof.verify.engine.GroundingIndex", unexpected_grounding)
    with pytest.raises(ValueError) as error:
        verify(data, document)
    path = 'groups["x\\\"].items[0]"][0].description'
    assert str(error.value).startswith(f"claim at {path!r} has unsupported value type dict")


@pytest.mark.parametrize("wrapper", [EvidencedDate, EvidencedText])
def test_mutated_explicit_string_kind_cannot_silently_verify_as_a_number(document, wrapper):
    schema = create_model("Claim", account=(wrapper, ...))
    data = schema(account=wrapper(value="2026-05-01", evidence=["13"]))
    data.account.value = 13
    with pytest.raises(ValueError, match="claim at 'account' declares a string kind"):
        verify(data, document)
    assert data.account.value == 13


def test_mutated_generic_wrapper_cannot_verify_an_object(document):
    class Claim(BaseModel):
        account: Evidenced[str]

    data = Claim(account=Evidenced[str](value="Example Works", evidence=["Example Works"]))
    data.account.value = {"account": "UNSUPPORTED"}
    with pytest.raises(ValueError, match="unsupported value type dict"):
        verify(data, document)
    assert data.account.value == {"account": "UNSUPPORTED"}


@pytest.mark.parametrize(
    ("annotation", "value", "quote"),
    [
        (str, "Example Works", "Example Works"),
        (int, 13, "13"),
        (float, 13.0, "13"),
        (bool, True, "Approval: yes"),
        (str | None, "Example Works", "Example Works"),
        (Any, "Example Works", "Example Works"),
        (TextChoice, "Example Works", "Example Works"),
        (NumberChoice, 13, "13"),
    ],
)
def test_supported_actual_values_still_use_their_evidence_checks(
    document, annotation, value, quote,
):
    schema = create_model("Claim", account=(Evidenced[annotation], ...))
    data = schema.model_validate({"account": {"value": value, "evidence": [quote]}})
    (field,) = verify(data, document).fields
    assert field.status == "verified" and field.rects and field.matched_text == quote
    assert field.value == data.account.value


def test_optional_absent_wrapper_and_containers_outside_wrappers_remain_supported(document):
    class Claim(BaseModel):
        absent: Evidenced[str] | None = None
        accounts: dict[str, Evidenced[str]]

    data = Claim.model_validate({
        "accounts": {
            "valid": {"value": "Example Works", "evidence": ["Example Works"]},
            "wrong": {"value": "UNSUPPORTED", "evidence": ["Example Works"]},
            "missing": {"value": "UNSUPPORTED"},
        },
    })
    report = verify(data, document)
    assert [field.path for field in report.fields] == [
        'accounts["valid"]', 'accounts["wrong"]', 'accounts["missing"]',
    ]
    assert report.counts == {"verified": 1, "needs_review": 1, "unsupported": 1}
