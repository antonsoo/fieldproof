"""Locale punctuation is part of a number, never a source of smaller amounts."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel

from fieldproof.document.loader import load_pdf
from fieldproof.document.model import Document
from fieldproof.ground.values import amount_readings, number_readings, number_style, number_tokens
from fieldproof.schemas import Evidenced
from fieldproof.verify import verify
from fieldproof.verify.value_checks import check_number, parse_all_numbers

STUDY = Path(__file__).resolve().parents[1] / "studies/arabic-numbers"
CASES = json.loads((STUDY / "intl.json").read_text())["cases"]


class Amount(BaseModel):
    total: Evidenced[float]


class IntegerAmount(BaseModel):
    total: Evidenced[int]


@pytest.fixture(scope="module")
def locale_pdf():
    return load_pdf(STUDY / "fixtures/numbers.pdf")


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_native_formatter_values_through_the_pdf_loader(case, locale_pdf):
    page = CASES.index(case) + 1
    quote = case["id"] + " total: " + case["numericText"]
    assert locale_pdf.page(page).text.endswith(quote)
    schema = IntegerAmount if case.get("integer") else Amount
    if case.get("percent"):
        values = [12, 5, 12.5]
    else:
        correct = int(case["input"]) if case.get("integer") else float(case["input"])
        readings = amount_readings(case["numericText"])
        assert len(readings) == 1 and readings[0].value == Decimal(case["input"])
        values = [correct, 234] if correct != 234 else [correct, 56]
    for value in values:
        claim = schema(total={"value": value, "evidence": [quote], "page": page})
        (field,) = verify(claim, locale_pdf).fields
        expected = "verified" if not case.get("percent") and value == correct else "needs_review"
        assert field.status.value == expected, field.reasons
        assert field.page == page and field.rects


@pytest.mark.parametrize("text", ["1٬234٫56", "١٬٢٣٤٫٥٦", "۱٬۲۳۴٫۵۶"])
def test_a_grouped_amount_has_one_value_and_one_source_span(text):
    (token,) = number_tokens("Total " + text)
    assert (token.start, token.end) == (6, 6 + len(text))
    assert parse_all_numbers(text) == [1234.56]
    assert check_number(1234.56, text).supported
    for fragment in [1, 234, 56]:
        assert not check_number(fragment, text).supported


@pytest.mark.parametrize(
    "text",
    [
        "1٬23",
        "1٬234,56",
        "1,234٫56",
        "1٬234.56",
        "1٫2٫3",
        "٬234",
        "1٫25e3",
        "AB1٬234٫56CD",
        "١٢٣_٤٥٦",
        "1٬234٫56/2",
    ],
)
def test_unsupported_mixed_or_identifier_spellings_supply_no_fragment(text):
    assert parse_all_numbers(text) == []


@pytest.mark.parametrize("sign", ["%", "‰", "‱", "٪", "؉", "؊"])
def test_rate_marks_exclude_the_whole_number_from_amounts(sign):
    for text in [f"١٢٫٥{sign}", f"١٢٫٥ {sign}", f"(١٢٫٥{sign})", f"{sign}١٢٫٥"]:
        assert parse_all_numbers(text) == []
        assert not check_number(12, text).supported
        assert not check_number(5, text).supported
        assert not check_number(12.5, text).supported


def test_explicit_arabic_symbols_do_not_set_a_latin_separator_convention():
    assert number_style("١٬٢٣٤٫٥٦ Total 60.000") is None
    assert [r.value for r in number_readings("١٬٢٣٤٫٥٦", "thousands")] == [Decimal("1234.56")]
    assert check_number(-1234.56, "Total −١٬٢٣٤٫٥٦").supported
    assert check_number(-1234.56, "Total (١٬٢٣٤٫٥٦)").supported
    assert not check_number(1234.56, "Total (١٬٢٣٤٫٥٦)").supported
    assert check_number(0.5, "Total ٫٥٠").supported


def test_rates_do_not_displace_separate_amounts_or_cross_a_line():
    assert parse_all_numbers("Tax ١٢٫٥٪ ١٬٢٣٤٫٥٦") == [1234.56]
    assert parse_all_numbers("Total ١٢٫٥\n٪ footer") == [12.5]
    assert parse_all_numbers("Fuel surcharge 1 210.50 210.50") == [1, 210.5, 210.5]


def test_a_clipped_percentage_quote_keeps_its_rate_mark_in_review(locale_pdf):
    page = locale_pdf.page(7)
    document = Document("isolated percentage page", [page])
    (field,) = verify(
        Amount(total={"value": 12.5, "evidence": ["١٢٫٥"], "page": 7}), document
    ).fields
    assert field.status.value == "needs_review"
    assert field.matched_text == "١٢٫٥٪" and field.rects
