"""A value is supported by a whole printed number, never a convenient fragment.

The PDF cases are hand-specified examples, not samples of extraction accuracy. They
pass through the actual text loader, quote aligner and verifier, including page boxes.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
import reportlab
from pydantic import BaseModel
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from fieldproof.document.loader import load_pdf
from fieldproof.ground.align import find_candidates
from fieldproof.ground.values import number_style
from fieldproof.schemas import Evidenced
from fieldproof.verify.engine import verify
from fieldproof.verify.value_checks import check_number, parse_all_numbers

CASES = json.loads((Path(__file__).parents[1] / "studies/numeric-evidence/cases.json").read_text())


class Amount(BaseModel):
    total: Evidenced[float]


class IntegerAmount(BaseModel):
    total: Evidenced[int]


@pytest.fixture(scope="module", autouse=True)
def numeric_font() -> None:
    # A bundled TrueType font preserves U+2212 as text in the generated PDF. The
    # base PDF fonts would silently replace it, hiding the bug from the loader.
    pdfmetrics.registerFont(
        TTFont("NumericEvidence", str(Path(reportlab.__file__).parent / "fonts/Vera.ttf"))
    )


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_number_evidence_through_actual_pdf(case: dict) -> None:
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=(612, 792), invariant=True)
    canvas.setFont("NumericEvidence", 12)
    canvas.drawString(36, 700, case["source"])
    canvas.save()
    document = load_pdf(stream.getvalue())
    assert document.pages[0].text == case["source"]
    schema = IntegerAmount if case.get("type") == "int" else Amount
    extracted = schema(total={"value": case["value"], "evidence": [case["quote"]], "page": 1})
    (result,) = verify(extracted, document).fields
    assert result.status.value == case["expect"], result.reasons
    assert result.page == 1 and len(result.rects) == 1
    assert result.matched_text in document.pages[0].text
    if case["expect"] == "needs_review":
        assert result.reasons
        # A clipped quote may no longer be used as a positive amount. Its match
        # must cover the source modifier, so the review highlight exposes it.
        if case["id"].endswith("omitted"):
            assert result.matched_text == case["source"].removeprefix("Total ")
            rect = result.rects[0]
            for word in document.pages[0].words[1:]:
                assert rect["x0"] <= word.bbox.x0 < word.bbox.x1 <= rect["x1"]


@pytest.mark.parametrize("spelling", ["++100", "--100", "(-100)", "(100", "100)", "100e+"])
def test_unsupported_or_malformed_spelling_is_not_repaired_into_an_amount(spelling: str) -> None:
    assert not check_number(100, spelling).supported
    assert not check_number(-100, spelling).supported


@pytest.mark.parametrize("spelling", ["1e6", "1e-6", "AB123CD", "123_456", "12:30", "1/2"])
def test_unsupported_numeric_tokens_do_not_leak_any_fragments(spelling: str) -> None:
    assert parse_all_numbers(spelling) == []


def test_nonfinite_values_never_verify() -> None:
    for value in (float("nan"), float("inf"), float("-inf")):
        assert not check_number(value, "Total 100.00").supported


@pytest.mark.parametrize("spelling", ["10²", "10₂", "½", "①"])
def test_unicode_numeric_notation_is_not_flattened_into_a_decimal(spelling: str) -> None:
    assert parse_all_numbers(spelling) == []


def test_identifier_or_exponent_cannot_set_the_documents_number_convention() -> None:
    assert number_style("Reference AB1.234,50CD TOTAL 60.000") is None
    assert number_style("Reference 1,234.50e6 TOTAL 60.000") is None
    assert number_style("Reference 123 TOTAL 1.234,50") == "thousands"
    assert number_style("Reference 123 TOTAL 1,234.50") == "decimal"


def test_accounting_parentheses_are_not_punctuation_to_discard() -> None:
    # Parentheses can also be prose around quantities. Without semantic context,
    # the amount parser treats a wrapped number as accounting notation; leaving
    # out the parentheses cannot silently turn it into a positive amount.
    assert check_number(-2, "(2)").supported
    assert not check_number(2, "(2)").supported


def test_count_notation_remains_supported_as_a_whole_token() -> None:
    assert check_number(2, "Qty 2x").supported
    assert check_number(2, "Qty x2").supported
    assert check_number(2, "Qty 2X").supported
    assert not check_number(2, "SKU AB2X").supported
    assert not check_number(2, "Size 2x3").supported


def test_a_following_negative_amount_keeps_its_own_sign() -> None:
    assert parse_all_numbers("Subtotal 18,182 - 15% DISC") == [18182]
    assert parse_all_numbers("Original 100.00 - $20.00") == [100, -20]


def test_rejecting_a_clipped_rate_does_not_make_an_unrelated_number_unique() -> None:
    stream = BytesIO()
    canvas = Canvas(stream)
    canvas.drawString(36, 700, "Tax 6% Reference 6")
    canvas.save()
    document = load_pdf(stream.getvalue())
    candidates = find_candidates("6", document.pages[0])
    assert [match.matched_text for match in candidates] == ["6%", "6"]
    assert [match.is_strong for match in candidates] == [False, True]
    data = Amount(total=Evidenced(value=6, evidence=["6"]))
    (result,) = verify(data, document).fields
    assert result.status.value == "needs_review" and "ambiguous" in result.reasons[0]


@pytest.mark.parametrize("quote", ["Total 100.00", "Total 100.00 - Footer"])
def test_a_footer_dash_does_not_negate_the_total_on_the_previous_line(quote: str) -> None:
    stream = BytesIO()
    canvas = Canvas(stream)
    canvas.drawString(36, 700, "Total 100.00")
    canvas.drawString(36, 660, "- Footer")
    canvas.save()
    document = load_pdf(stream.getvalue())
    (result,) = verify(Amount(total=Evidenced(value=100, evidence=[quote])), document).fields
    assert result.status.value == "verified", result.reasons
    assert result.matched_text == quote  # The evidence itself keeps its original offsets.
