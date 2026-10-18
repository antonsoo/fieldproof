"""A fraction is not evidence for either of its integer components."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from fieldproof.document.loader import load_pdf
from fieldproof.document.model import Document
from fieldproof.ground.values import number_tokens
from fieldproof.schemas import Evidenced
from fieldproof.verify import verify
from fieldproof.verify.value_checks import check_number, parse_all_numbers


class Quantity(BaseModel):
    quantity: Evidenced[float]


HERE = Path(__file__).resolve().parents[1] / "studies/fraction-evidence/fixtures"
CASES = json.loads((HERE / "cases.json").read_text())


@pytest.mark.parametrize("case", CASES)
def test_fraction_components_cannot_verify_through_the_native_pdf_loader(case):
    slash, gap, text = case["slash"], case["gap"], case["text"]
    page = load_pdf(HERE / "fractions.pdf").pages[CASES.index(case)]
    document = Document("isolated authored control", [page])
    assert document.pages[0].text == text
    for value in (1, 2, 0.5):
        for quote in (text, f"1{gap}{slash}{gap}2", str(int(value)) if value != 0.5 else "0.5"):
            claim = Quantity(quantity=Evidenced(value=value, evidence=[quote]))
            field = verify(claim, document).fields[0]
            assert field.status.value != "verified", (value, quote, field.reasons)
    (token,) = number_tokens(text)
    assert text[token.start : token.end] == f"1{gap}{slash}{gap}2"
    assert token.readings() == []


@pytest.mark.parametrize(
    "text",
    [
        "1⁄2",
        "1∕2",
        "1 / 2",
        "1/ 2",
        "1 /2",
        "1 1⁄2",
        "½",
        "1½",
        "(1 ⁄ 2)",
        "-1∕2",
        "2026 / 10 / 17",
    ],
)
def test_whole_unsupported_spelling_leaks_no_numerator_denominator_or_year(text):
    assert parse_all_numbers(text) == []
    for value in (1, 2, 0.5, 10, 17, 2026):
        assert not check_number(value, text).supported


def test_a_separate_quantity_and_price_are_not_removed_by_a_fraction_elsewhere():
    assert parse_all_numbers("Qty 3; cut length 1⁄2 m; unit price $19.95") == [3, 19.95]
    assert check_number(3, "Qty 3; cut length 1⁄2 m").supported
    assert check_number(19.95, "Cut length 1⁄2 m; unit price $19.95").supported


def test_numeric_dates_keep_their_existing_boundary_instead_of_borrowing_a_dash():
    # A full real-receipt replay exposed a dash being added to a date's weak
    # match after slash expressions became tokens. The date parser owns it.
    assert number_tokens("Date - 25/06/18") == ()
