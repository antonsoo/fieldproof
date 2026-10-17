"""A grouping space must not certify an amount carved out of the printed number."""

from __future__ import annotations

import json
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from pydantic import BaseModel
from reportlab.pdfgen.canvas import Canvas

from fieldproof.document.loader import load_pdf
from fieldproof.document.model import BBox, Document
from fieldproof.ground.lines import separate_numeric_regions
from fieldproof.ground.values import number_style, number_tokens
from fieldproof.schemas import Evidenced
from fieldproof.schemas.base import EvidencedDate
from fieldproof.verify import verify
from fieldproof.verify.value_checks import check_number, parse_all_numbers

HERE = Path(__file__).resolve().parents[1] / "studies/spaced-numbers"
CASES = json.loads((HERE / "cases.json").read_text())


class Amount(BaseModel):
    total: Evidenced[float]


@pytest.fixture(scope="module")
def numbers_pdf():
    return load_pdf(HERE / "fixtures/numbers.pdf")


@pytest.mark.parametrize("separator", [" ", "\u00a0", "\u202f", "\u2009", "   "])
@pytest.mark.parametrize("digits", ["1{0}234,56", "1{0}234{0}567.89", "1{0}23{0}456,78"])
def test_grouping_spaces_keep_one_unresolved_source_span(separator, digits):
    text = "Total ($ " + digits.format(separator) + ")"
    (token,) = number_tokens(text)
    assert token.ambiguous_spacing and token.readings() == []
    assert text[token.start : token.end] == text.removeprefix("Total ")
    assert parse_all_numbers(text) == []
    for value in [1, 23, 234, 56, 234.56, 1234.56, -1234.56]:
        result = check_number(value, text)
        assert not result.supported and "clear boundary" in result.reason


@pytest.mark.parametrize("text", ["1 234e6", "1 234/5", "1 234abc", "1 234,5,6"])
def test_malformed_spaced_spellings_cannot_leave_the_first_group_as_evidence(text):
    assert not check_number(1, text).supported
    (token,) = number_tokens(text)
    assert token.start == 0 and token.end >= 5 and token.ambiguous_spacing


@pytest.mark.parametrize("page_number", range(1, 21))
def test_native_locale_and_authored_grouping_controls_through_pdf(page_number, numbers_pdf):
    page = numbers_pdf.page(page_number)
    case = CASES[page_number - 1]
    quote = "Total " + " ".join(case["text"].split())
    document = Document("isolated control", [page])
    if case.get("input") is not None:
        value = float(case["input"])
        (field,) = verify(Amount(total={"value": value, "evidence": [quote]}), document).fields
        expected = (
            "needs_review"
            if " " in case["text"] or any(c.isspace() for c in case["text"])
            else "verified"
        )
        assert field.status.value == expected, field.reasons
        assert field.page == page_number and field.rects
    for value in [1, 234, 56, 234.56]:
        (field,) = verify(Amount(total={"value": value, "evidence": [quote]}), document).fields
        assert field.status.value == "needs_review", field.reasons


@pytest.mark.parametrize("quote,value", [("1", 1), ("234,56", 234.56), ("1 234,56", 1234.56)])
def test_clipped_numeric_quotes_retain_the_uncertain_group_in_review(quote, value, numbers_pdf):
    page = numbers_pdf.page(16)  # ASCII grouping control, no Unicode normalization dependence.
    (field,) = verify(
        Amount(total={"value": value, "evidence": [quote]}), Document("control", [page])
    ).fields
    assert field.status.value == "needs_review"
    assert field.matched_text == "1 234,56"
    assert field.rects and "clear boundary" in field.reasons[-1]
    for word in page.words[-2:]:
        rect = field.rects[0]
        assert rect["x0"] <= word.bbox.x0 < word.bbox.x1 <= rect["x1"]


def test_identical_flattened_rows_have_different_quantity_evidence(numbers_pdf):
    wide, tight = numbers_pdf.pages[-2:]
    row = "Fuel surcharge 1 210.50 210.50"
    assert wide.text.endswith(row) and tight.text.endswith(row)
    for page, expected in [(wide, "verified"), (tight, "needs_review")]:
        for quote in [row, "1"]:
            (field,) = verify(
                Amount(total={"value": 1, "evidence": [quote]}), Document("row", [page])
            ).fields
            assert field.status.value == expected, field.reasons
        for value, status in [(210.5, "verified"), (1210.5, "needs_review")]:
            (field,) = verify(
                Amount(total={"value": value, "evidence": [row]}), Document("row", [page])
            ).fields
            assert field.status.value == status, field.reasons


@pytest.mark.parametrize("bad", [BBox(0, 0, 0, 10), BBox(float("nan"), 0, 1, 10)])
def test_invalid_geometry_does_not_establish_a_numeric_boundary(bad, numbers_pdf):
    page = numbers_pdf.pages[-2]
    words = list(page.words[-5:])
    words[2] = replace(words[2], bbox=bad)
    numeric = separate_numeric_regions(page.text, words)
    assert not check_number(1, numeric.split("Fuel surcharge")[-1]).supported


def test_spacing_preserves_tabs_lines_explicit_units_and_other_numeric_conventions():
    assert parse_all_numbers("1\t234,56\n789,01") == [1, 234.56, 789.01]
    assert parse_all_numbers("1 $234.56") == [1, 234.56]
    assert parse_all_numbers("1x 234.56") == [1, 234.56]
    assert parse_all_numbers("1.50 234.56") == [1.5, 234.56]
    assert number_style("1 234,56 total 60.000") is None
    assert number_style("1\t1.234,56 total 60.000") == "thousands"


def test_a_wide_gap_does_not_strip_a_same_row_numeric_sign(numbers_pdf):
    page = numbers_pdf.pages[-2]
    quantity = page.words[-3]
    sign = replace(quantity, text="-", start=0, end=1, bbox=BBox(0, 0, 5, 12))
    amount = replace(quantity, text="100.00", start=2, end=8, bbox=BBox(100, 0, 140, 12))
    numeric = separate_numeric_regions("- 100.00", [sign, amount])
    assert check_number(-100, numeric).supported
    assert not check_number(100, numeric).supported


@pytest.mark.parametrize(
    "date_text", ["14-02-2018", "14/02/2018", "2018-02-14", "14 February 2018", "February 14, 2018"]
)
def test_the_end_of_a_date_and_start_of_a_time_are_not_numeric_groups(date_text):
    class Dated(BaseModel):
        issued: EvidencedDate

    stream = BytesIO()
    canvas = Canvas(stream, invariant=True)
    canvas.drawString(40, 700, "DATE : " + date_text + " 13:45")
    canvas.save()
    document = load_pdf(stream.getvalue())
    (field,) = verify(
        Dated(issued={"value": "2018-02-14", "evidence": ["DATE : " + date_text]}), document
    ).fields
    assert field.status.value == "verified", field.reasons
    assert field.matched_text == "DATE : " + date_text


def test_a_date_or_clock_boundary_does_not_discard_an_earlier_uncertain_group():
    assert parse_all_numbers("1 2018-02-14") == [1]
    assert not check_number(234.56, "Total 1 234,56 13:45").supported
    assert not check_number(1234.56, "Total 1 234,56 2018-02-14").supported


@pytest.mark.parametrize("text", ["DATE 14-02-2018 13:45", "At 13:45 100.00", "Ref ID-1 234"])
def test_group_scan_does_not_start_inside_a_date_time_or_identifier(text):
    assert not any(t.ambiguous_spacing for t in number_tokens(text))
