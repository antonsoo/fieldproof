"""A printed written date cannot lose digits before a claim is verified."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from fieldproof.document.loader import load_pdf
from fieldproof.ground.values import dates_in, whole_date
from fieldproof.schemas.contract import ContractKeyTerms
from fieldproof.verify.engine import verify
from fieldproof.verify.value_checks import check_date, parse_date


@pytest.mark.parametrize("token", [
    "May 1, 20260", "1 May 20260", "111 May 2026", "001 May 2026",
    "May 1, 2026X", "May 1, 2026_ref", "XMay 1, 2026", "X1 May 2026",
    "ref-May 1, 2026", "May 1, 2026-X", "May 1, 2026/99", "May 1, 2026.7",
])
def test_date_fragments_are_rejected_by_grounding_and_value_checks(token: str) -> None:
    text = f"Effective date: {token}"
    assert dates_in(text) == []
    assert parse_date(text) is None
    assert not check_date("2026-05-01", text).supported


@pytest.mark.parametrize("spelling", [
    "May 1, 2026", "May 1 2026", "MAY 1, 2026", "1 May 2026", "May. 1, 2026",
])
def test_supported_written_spellings_have_consistent_value_checks(spelling: str) -> None:
    expected = date(2026, 5, 1)
    assert whole_date(spelling) == {expected}
    for text in (spelling, f"Effective: {spelling}.", f"({spelling})"):
        assert parse_date(text) == expected
        assert check_date(expected.isoformat(), text).supported


def test_actual_pdf_keeps_the_malformed_year_in_review_evidence() -> None:
    root = Path(__file__).parents[1] / "studies/written-dates"
    fixture = json.loads((root / "extra-year-digit.json").read_text())
    document = load_pdf(root / "extra-year-digit.pdf")
    result = verify(ContractKeyTerms.model_validate(fixture["data"]), document)
    field = next(f for f in result.fields if f.path == "effective_date")
    assert field.status == "needs_review"
    assert field.matched_text == "Effective date: May 1, 20260"
    assert field.page == 1 and field.rects and field.match_score == 100
    assert result.counts == {"verified": 2, "needs_review": 1, "unsupported": 0}
