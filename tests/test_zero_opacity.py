"""Transparent native text must not become visible document evidence."""

from __future__ import annotations

import importlib.util
import io
import json
from dataclasses import asdict
from pathlib import Path

import pytest
from pydantic import BaseModel
from reportlab.pdfgen.canvas import Canvas

from fieldproof.document.loader import load_pdf
from fieldproof.document.model import document_from_dict
from fieldproof.schemas import Evidenced
from fieldproof.verify import RowEvidenceRule, verify

STUDY = Path(__file__).parents[1] / "studies/zero-opacity"


class Claim(BaseModel):
    total: Evidenced[float]


def test_authored_fill_stroke_form_group_and_rotation_controls() -> None:
    spec = importlib.util.spec_from_file_location("zero_opacity_replay", STUDY / "replay.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.replay()
    assert result["claims"] == 84
    assert result["mismatches"] == 0, result["observations"]


def test_transparency_survives_worker_transport_and_legacy_documents() -> None:
    document = load_pdf(STUDY / "fixtures/form-inherited.pdf")
    encoded = json.loads(json.dumps(asdict(document)))
    assert document_from_dict(encoded) == document
    hidden = [word for word in document.pages[0].words if word.zero_opacity]
    assert [word.text for word in hidden] == ["Authorized", "total:", "$900.00"]
    assert all(word.unpainted and word.render_mode == 0 for word in hidden)
    for word in encoded["pages"][0]["words"]:
        word.pop("zero_opacity")
    assert not any(word.zero_opacity for word in document_from_dict(encoded).pages[0].words)


def test_opacity_change_inside_a_word_does_not_disappear_in_segmentation() -> None:
    stream = io.BytesIO()
    pdf = Canvas(stream, invariant=True)
    item = pdf.beginText(40, 700)
    item.textOut("Ac")
    item.setFillAlpha(0)
    item.textOut("me")
    item.setFillAlpha(1)
    item.textOut(" Services")
    pdf.drawText(item)
    pdf.save()
    document = load_pdf(stream.getvalue())
    assert any(word.text == "me" and word.zero_opacity for word in document.pages[0].words)

    class Name(BaseModel):
        name: Evidenced[str]

    report = verify(Name(name=Evidenced(value="Acme Services", evidence=["Acme Services"])),
                    document, text_edit_tolerance=2)
    assert report.fields[0].status == "needs_review"
    assert any("zero opacity" in reason for reason in report.fields[0].reasons)


@pytest.mark.parametrize("kind", ["number", "date"])
def test_transparent_hints_do_not_set_document_conventions(kind: str) -> None:
    stream = io.BytesIO()
    pdf = Canvas(stream, invariant=True)
    source, hint = ("Amount due: 60.000", "Reference: 1.234,50") if kind == "number" else (
        "Issue date: 03/04/2026", "Reference date: 31/12/2026"
    )
    pdf.drawString(40, 700, source)
    pdf.setFillAlpha(0)
    pdf.drawString(40, 600, hint)
    pdf.save()
    document = load_pdf(stream.getvalue())
    if kind == "number":
        claims = [Claim(total=Evidenced(value=value, evidence=[source])) for value in (60, 60000)]
    else:
        class DateClaim(BaseModel):
            issue_date: Evidenced[str]

        claims = [DateClaim(issue_date=Evidenced(value=value, evidence=[source]))
                  for value in ("2026-03-04", "2026-04-03")]
    for claim in claims:
        (result,) = verify(claim, document).fields
        assert result.status == "needs_review"


def test_hidden_description_cannot_select_a_repeated_quantity_as_its_row() -> None:
    class Item(BaseModel):
        description: Evidenced[str]
        quantity: Evidenced[float]

    class Rows(BaseModel):
        items: list[Item]

    stream = io.BytesIO()
    pdf = Canvas(stream, invariant=True)
    pdf.saveState()
    pdf.setFillAlpha(0)
    pdf.drawString(40, 700, "Delivery")
    pdf.restoreState()
    pdf.drawString(200, 700, "2")
    pdf.drawString(40, 600, "Packing 2")
    pdf.save()
    claim = Rows(items=[Item(description=Evidenced(value="Delivery", evidence=["Delivery"]),
                            quantity=Evidenced(value=2, evidence=["2"]))])
    report = verify(claim, load_pdf(stream.getvalue()), row_rules=[
        RowEvidenceRule("items", "description", ("quantity",))
    ])
    assert all(field.status == "needs_review" for field in report.fields)
    assert "no strongly grounded" in report.fields[1].reasons[0]


def test_a_transparent_header_cannot_establish_column_roles() -> None:
    # Use the realistic invoice layout already exercised by the column study.
    from test_column_evidence import specimen

    data, _ = specimen()
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=(612, 792), invariant=True)
    pdf.saveState()
    pdf.setFillAlpha(0)
    for x, label in [(48, "Description"), (310, "Qty"), (400, "Unit price"), (510, "Amount")]:
        pdf.drawString(x, 700, label)
    pdf.restoreState()
    for x, value in zip((48, 310, 400, 510), ("Delivery-A", "3", "12.50", "37.50"), strict=True):
        pdf.drawString(x, 670, value)
    pdf.save()
    report = verify(data, load_pdf(stream.getvalue()))
    assert report.column_checks
    assert all(check.status == "unavailable" for check in report.column_checks)
