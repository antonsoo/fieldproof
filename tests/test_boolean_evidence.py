"""Boolean claims through the actual PDF loader, grounding and generic verifier."""

from __future__ import annotations

from io import BytesIO

import pytest
from pydantic import BaseModel
from reportlab.pdfgen.canvas import Canvas

from fieldproof.document.loader import load_pdf
from fieldproof.schemas import Evidenced
from fieldproof.verify.engine import FieldStatus, verify


class Approval(BaseModel):
    approved: Evidenced[bool]


@pytest.mark.parametrize(
    ("quote", "answer"),
    [
        ("The request is approved, not denied.", None),
        ("No changes: approval confirmed.", None),
        ("Approval was denied previously, but is confirmed today.", None),
        ("The request is not approved.", None),
        ("Approval: yes or no", None),
        ("Approved: yes; Renewal: no", None),
        ("Approval: YES", True),
        ("Approval = true.", True),
        ("Approval: no", False),
        ("Approval = FALSE", False),
    ],
)
def test_boolean_pdf_keeps_its_evidence_without_guessing_an_answer(
    quote: str, answer: bool | None
) -> None:
    output = BytesIO()
    canvas = Canvas(output, invariant=True)
    canvas.drawString(40, 740, quote)
    canvas.save()
    document = load_pdf(output.getvalue())
    for value in (False, True):
        report = verify(
            Approval(approved=Evidenced(value=value, evidence=[quote], page=1)), document
        )
        field = report.fields[0]
        expected = FieldStatus.VERIFIED if value is answer else FieldStatus.NEEDS_REVIEW
        assert field.status == expected
        assert field.matched_text == quote
        assert field.match_score == 100
        assert field.page == 1 and field.rects
        assert type(field.to_dict()["value"]) is bool
        if expected == FieldStatus.NEEDS_REVIEW:
            assert field.reasons
