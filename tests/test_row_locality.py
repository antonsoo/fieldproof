"""Repeated evidence must not acquire authority from an unrelated location."""

from dataclasses import replace
from io import BytesIO
from itertools import permutations

import pytest
from pydantic import BaseModel
from reportlab.pdfgen.canvas import Canvas

from fieldproof.document.loader import load_pdf
from fieldproof.document.model import BBox, Word
from fieldproof.ground.align import GroundingMatch, unique_row_candidate
from fieldproof.schemas import Evidenced
from fieldproof.verify.engine import verify


class Row(BaseModel):
    description: Evidenced[str]
    quantity: Evidenced[float]


class Form(BaseModel):
    rows: list[Row]


@pytest.mark.parametrize("elsewhere", ["next_line", "next_page", "same_line_tie", "skewed_tie"])
def test_real_pdf_never_chooses_an_unresolved_quantity(elsewhere: str) -> None:
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=(612, 792), invariant=True)
    canvas.drawString(50, 700, "Delivery")
    if elsewhere == "next_page":
        canvas.showPage()
    y = 686 if elsewhere == "next_line" else 700
    canvas.drawString(250, y, "1")
    canvas.drawString(350, y - (3 if elsewhere == "skewed_tie" else 0), "1")
    canvas.save()
    report = verify(
        Form(
            rows=[
                Row(
                    description=Evidenced(value="Delivery", evidence=["Delivery"]),
                    quantity=Evidenced(value=1, evidence=["1"]),
                )
            ]
        ),
        load_pdf(stream.getvalue()),
    )
    result = report.fields[1]
    assert result.status == "needs_review"
    assert result.page is None and result.rects == []
    assert "no unique occurrence" in result.reasons[0]


@pytest.mark.parametrize(
    "kind", ["wrong_value", "wrong_quote", "accepted_quote_edit", "accepted_value_edit"]
)
def test_a_review_or_edited_description_cannot_anchor_another_field(kind: str) -> None:
    text = "International delivery"
    changed = "International deliverx"
    stream = BytesIO()
    canvas = Canvas(stream, invariant=True)
    canvas.drawString(50, 700, f"{text} 1")
    canvas.drawString(50, 600, "Packing 1")
    canvas.save()
    quote = changed if kind in ("wrong_quote", "accepted_quote_edit") else text
    value = changed if kind in ("wrong_value", "accepted_value_edit") else text
    report = verify(
        Form(
            rows=[
                Row(
                    description=Evidenced(value=value, evidence=[quote]),
                    quantity=Evidenced(value=1, evidence=["1"]),
                )
            ]
        ),
        load_pdf(stream.getvalue()),
        text_edit_tolerance=1 if kind.startswith("accepted") else 0,
    )
    if kind.startswith("accepted"):
        assert report.fields[0].status == "verified"
        assert report.fields[0].notes
    assert report.fields[1].status == "needs_review"
    assert "no strongly grounded" in report.fields[1].reasons[0]


def match(page: int, x: float, y: float, height: float = 12) -> GroundingMatch:
    return GroundingMatch(
        "1",
        page,
        int(x),
        int(x) + 1,
        100,
        "1",
        (Word("1", BBox(x, y, x + 8, y + height), int(x), int(x) + 1),),
    )


def test_location_selection_is_order_and_scale_independent() -> None:
    # Geometric scaling must not turn an OCR-pixel document into a different
    # answer from its PDF-point equivalent; input order must not break ties.
    for scale in (0.1, 1, 3, 100):
        anchor = match(1, 10 * scale, 50 * scale, 12 * scale)
        right = match(1, 200 * scale, 53 * scale, 12 * scale)
        next_line = match(1, 200 * scale, 64 * scale, 12 * scale)
        next_page = match(2, 200 * scale, 50 * scale, 12 * scale)
        for candidates in permutations([right, next_line, next_page]):
            assert unique_row_candidate(list(candidates), anchor) is right
        tied = match(1, 300 * scale, 50 * scale, 12 * scale)
        for candidates in permutations([right, tied, next_page]):
            assert unique_row_candidate(list(candidates), anchor) is None


def test_multiline_or_unusable_geometry_cannot_establish_a_row() -> None:
    anchor = match(1, 10, 50)
    right = match(1, 200, 50)
    second_line = match(1, 10, 90)
    multiline = replace(anchor, words=anchor.words + second_line.words)
    for hint in (
        multiline,
        replace(anchor, words=()),
        match(1, 10, float("nan")),
        match(1, 10, 50, 0),
        match(1, 10, 50, -12),
    ):
        assert unique_row_candidate([right], hint) is None
    assert unique_row_candidate([multiline], anchor) is None
