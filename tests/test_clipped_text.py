"""Native PDF controls exercise clipping, verification and worker transport."""

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

STUDY = Path(__file__).parents[1] / "studies/clipped-text"


class Claim(BaseModel):
    total: Evidenced[float]


def test_authored_clipping_paths_forms_and_painted_controls() -> None:
    spec = importlib.util.spec_from_file_location("clipped_text_replay", STUDY / "replay.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.replay()
    assert result["claims"] == 138
    assert result["mismatches"] == 0, result["observations"]


def test_clipping_metadata_survives_json_and_legacy_documents() -> None:
    document = load_pdf(STUDY / "fixtures/form-nested.pdf")
    encoded = json.loads(json.dumps(asdict(document)))
    assert document_from_dict(encoded) == document
    affected = [word for word in document.pages[0].words if word.clip_risk]
    assert [word.text for word in affected] == ["Authorized", "total:", "$900.00"]
    assert all(word.paint_requires_review and not word.unpainted for word in affected)
    for word in encoded["pages"][0]["words"]:
        word.pop("clip_risk")
    assert not any(word.clip_risk for word in document_from_dict(encoded).pages[0].words)


@pytest.mark.parametrize("kind", ["number", "date"])
def test_clipped_hints_cannot_set_document_conventions(kind: str) -> None:
    stream = io.BytesIO()
    pdf = Canvas(stream, invariant=True)
    source, hint = ("Amount due: 60.000", "Reference: 1.234,50") if kind == "number" else (
        "Issue date: 03/04/2026", "Reference date: 31/12/2026"
    )
    pdf.drawString(40, 700, source)
    pdf.saveState()
    pdf._code.append("0 0 200 200 re W n")
    pdf.drawString(40, 600, hint)
    pdf.restoreState()
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


def test_partial_word_cannot_hide_the_clipping_flag_or_use_edit_tolerance() -> None:
    stream = io.BytesIO()
    pdf = Canvas(stream, invariant=True)
    # At 12 pt, "Ac" fits and the remaining "me" crosses this clip boundary.
    pdf._code.append("0 600 55 150 re W n")
    pdf.drawString(40, 700, "Acme Services")
    pdf.save()

    class Name(BaseModel):
        name: Evidenced[str]

    document = load_pdf(stream.getvalue())
    assert any(word.clip_risk for word in document.pages[0].words)
    report = verify(Name(name=Evidenced(value="Acme Services", evidence=["Acme Services"])),
                    document, text_edit_tolerance=2)
    assert report.fields[0].status == "needs_review"
    assert any("clipping boundary" in reason for reason in report.fields[0].reasons)


def test_clipped_row_anchor_cannot_disambiguate_a_repeated_quantity() -> None:
    class Item(BaseModel):
        description: Evidenced[str]
        quantity: Evidenced[float]

    class Rows(BaseModel):
        items: list[Item]

    stream = io.BytesIO()
    pdf = Canvas(stream, invariant=True)
    pdf.saveState()
    pdf._code.append("0 0 200 200 re W n")
    pdf.drawString(40, 700, "Delivery")
    pdf.restoreState()
    pdf.drawString(200, 700, "2")
    pdf.drawString(40, 600, "Packing 2")
    pdf.save()
    data = Rows(items=[Item(description=Evidenced(value="Delivery", evidence=["Delivery"]),
                           quantity=Evidenced(value=2, evidence=["2"]))])
    report = verify(data, load_pdf(stream.getvalue()), row_rules=[
        RowEvidenceRule("items", "description", ("quantity",))
    ])
    assert all(field.status == "needs_review" for field in report.fields)
    assert "no strongly grounded" in report.fields[1].reasons[0]


def test_clipped_headers_do_not_establish_visible_column_roles() -> None:
    from test_column_evidence import specimen

    data, _ = specimen()
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=(612, 792), invariant=True)
    pdf.saveState()
    pdf._code.append("0 0 200 200 re W n")
    for x, label in [(48, "Description"), (310, "Qty"), (400, "Unit price"), (510, "Amount")]:
        pdf.drawString(x, 700, label)
    pdf.restoreState()
    for x, value in zip((48, 310, 400, 510), ("Delivery-A", "3", "12.50", "37.50"), strict=True):
        pdf.drawString(x, 670, value)
    pdf.save()
    report = verify(data, load_pdf(stream.getvalue()))
    assert report.column_checks
    assert all(check.status == "unavailable" for check in report.column_checks)
