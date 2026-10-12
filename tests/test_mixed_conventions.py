"""Fallback settings cannot settle contradictory evidence in actual PDF text."""

from __future__ import annotations

from io import BytesIO

import pytest
from pydantic import BaseModel
from reportlab.pdfgen.canvas import Canvas

from fieldproof.document.loader import load_pdf
from fieldproof.document.model import Document
from fieldproof.ground.values import number_style, number_styles
from fieldproof.schemas import Evidenced
from fieldproof.verify.engine import FieldStatus, verify
from fieldproof.verify.value_checks import numeric_date_order, numeric_date_orders


class Claims(BaseModel):
    total: Evidenced[float]
    issue_date: Evidenced[str]
    explicit_amount: Evidenced[float]
    explicit_date: Evidenced[str]


def document(*context: str) -> Document:
    stream = BytesIO()
    canvas = Canvas(stream, invariant=True)
    lines = [
        "Total: 60.000",
        "Issue date: 03/04/2026",
        "Explicit amount: 17.50",
        "Explicit date: 2026-06-18",
        *context,
    ]
    for index, line in enumerate(lines):
        canvas.drawString(40, 740 - index * 30, line)
    canvas.save()
    return load_pdf(stream.getvalue())


def claims(amount: float, date: str) -> Claims:
    return Claims(
        total=Evidenced(value=amount, evidence=["Total: 60.000"], page=1),
        issue_date=Evidenced(value=date, evidence=["Issue date: 03/04/2026"], page=1),
        explicit_amount=Evidenced(value=17.5, evidence=["Explicit amount: 17.50"], page=1),
        explicit_date=Evidenced(value="2026-06-18", evidence=["Explicit date: 2026-06-18"], page=1),
    )


@pytest.mark.parametrize("style", [None, "decimal", "thousands"])
@pytest.mark.parametrize("order", [None, "mdy", "dmy"])
@pytest.mark.parametrize("amount,date", [(60, "2026-03-04"), (60000, "2026-04-03")])
def test_conflicting_conventions_need_review_regardless_of_defaults(style, order, amount, date):
    doc = document("US section: 1,234.50 on 12/31/2026", "EU section: 1.234,50 on 31/12/2026")
    report = verify(claims(amount, date), doc, default_number_style=style, default_date_order=order)
    total, issue_date, explicit_amount, explicit_date = report.fields
    for result in (total, issue_date):
        assert result.status is FieldStatus.NEEDS_REVIEW
        assert any("conflicting evidence" in reason for reason in result.reasons)
        assert result.page == 1 and result.rects
    assert total.matched_text == "Total: 60.000"
    assert issue_date.matched_text == "Issue date: 03/04/2026"
    assert explicit_amount.status is explicit_date.status is FieldStatus.VERIFIED


def test_absent_evidence_still_uses_defaults_and_unique_evidence_still_wins():
    claim = claims(60000, "2026-04-03")
    absent = document()
    assert [f.status for f in verify(claim, absent).fields[:2]] == [FieldStatus.NEEDS_REVIEW] * 2
    assert all(
        f.status is FieldStatus.VERIFIED
        for f in verify(
            claim, absent, default_number_style="thousands", default_date_order="dmy"
        ).fields
    )
    decisive = document("Reference amount: 1.234,50", "Reference date: 31/12/2026")
    assert all(
        f.status is FieldStatus.VERIFIED
        for f in verify(
            claim, decisive, default_number_style="decimal", default_date_order="mdy"
        ).fields
    )


def test_a_conflict_in_one_convention_does_not_disable_an_unrelated_default():
    claim = claims(60000, "2026-04-03")
    for context, expected in (
        (("1,234.50", "1.234,50"), [FieldStatus.NEEDS_REVIEW, FieldStatus.VERIFIED]),
        (("12/31/2026", "31/12/2026"), [FieldStatus.VERIFIED, FieldStatus.NEEDS_REVIEW]),
    ):
        result = verify(
            claim,
            document(*context),
            default_number_style="thousands",
            default_date_order="dmy",
        )
        assert [field.status for field in result.fields[:2]] == expected


def test_inference_retains_the_observed_sets_without_changing_unique_helpers():
    assert number_styles("60.000 and 17.50") == frozenset()
    assert numeric_date_orders("03/04/2026 and 2026-06-18") == frozenset()
    for text in ("1,234.50 and 1.234,50", "1.234,50 and 1,234.50"):
        assert number_styles(text) == {"decimal", "thousands"}
        assert number_style(text) is None
    for text in ("31/12/2026 and 12/31/2026", "12/31/2026 and 31/12/2026"):
        assert numeric_date_orders(text) == {"mdy", "dmy"}
        assert numeric_date_order(text) is None
