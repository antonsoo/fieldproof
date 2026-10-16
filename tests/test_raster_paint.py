"""Native final-pixel evidence, incomplete observations and trusted-context gates."""

from __future__ import annotations

import importlib.util
import io
import json
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import ImageChops
from pydantic import BaseModel
from reportlab.pdfgen.canvas import Canvas

from fieldproof.document.limits import DocumentLimitError, DocumentLimits
from fieldproof.document.loader import load_pdf
from fieldproof.document.model import document_from_dict
from fieldproof.document.raster_paint import _render_rgb, _suppress_text
from fieldproof.schemas import Evidenced
from fieldproof.verify import RowEvidenceRule, verify

STUDY = Path(__file__).parents[1] / "studies/flat-raster"


class Amount(BaseModel):
    total: Evidenced[float]


def test_authored_renders_grounding_and_geometry_through_worker_json() -> None:
    spec = importlib.util.spec_from_file_location("flat_raster_replay", STUDY / "replay.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.replay()
    assert result["claims"] == 102
    assert result["mismatches"] == 0, result["observations"]


def test_one_hidden_digit_marks_the_original_word_without_inserting_spaces() -> None:
    document = load_pdf(STUDY / "fixtures/leading-nine-hidden.pdf")
    assert document_from_dict(json.loads(json.dumps(asdict(document)))) == document
    word = next(w for w in document.pages[0].words if w.text == "$900.00")
    assert word.raster_state == "no_contribution"
    assert word.paint_requires_review and not word.unpainted and not word.clip_risk
    assert document.pages[0].text[word.start : word.end] == "$900.00"


def test_legacy_native_without_a_raster_observation_stays_unchecked() -> None:
    document = load_pdf(STUDY / "fixtures/black-on-white.pdf")
    raw = asdict(document)
    for word in raw["pages"][0]["words"]:
        word.pop("raster_state")
    legacy = document_from_dict(raw)
    data = Amount(total=Evidenced(value=900, evidence=["Authorized total: $900.00"]))
    assert verify(data, document).fields[0].status == "verified"
    result = verify(data, legacy).fields[0]
    assert result.status == "needs_review"
    assert any("without a completed" in reason for reason in result.reasons)
    assert all(word.raster_state is None for word in legacy.pages[0].words)


@pytest.mark.parametrize("kind", ["pixel-budget", "subpixel-glyphs"])
def test_unavailable_pixels_do_not_become_a_clean_observation(kind: str) -> None:
    stream = io.BytesIO()
    pdf = Canvas(
        stream, pagesize=(2500, 2500) if kind == "pixel-budget" else (612, 792), invariant=True
    )
    pdf.setFont("Helvetica", 0.1 if kind == "subpixel-glyphs" else 16)
    pdf.drawString(40, 600, "Authorized total: $900.00")
    pdf.save()
    content = stream.getvalue()
    document = load_pdf(content)
    assert document.pages[0].words
    assert all(w.raster_state == "unavailable" for w in document.pages[0].words)
    result = verify(
        Amount(total=Evidenced(value=900, evidence=["Authorized total: $900.00"])), document
    ).fields[0]
    assert result.status == "needs_review"
    if kind == "pixel-budget":
        # Existing opt-in intake limits still reject oversized pages before text
        # extraction; an unrestricted load retains text but cannot claim an audit.
        with pytest.raises(DocumentLimitError):
            load_pdf(content, limits=DocumentLimits())


@pytest.mark.parametrize("kind", ["number", "date"])
def test_flat_hints_cannot_set_document_conventions(kind: str) -> None:
    stream = io.BytesIO()
    pdf = Canvas(stream, invariant=True)
    source, hint = (
        ("Amount due: 60.000", "Reference: 1.234,50")
        if kind == "number"
        else ("Issue date: 03/04/2026", "Reference date: 31/12/2026")
    )
    pdf.drawString(40, 700, source)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.drawString(40, 600, hint)
    pdf.save()
    document = load_pdf(stream.getvalue())
    if kind == "number":
        claims = [Amount(total=Evidenced(value=v, evidence=[source])) for v in (60, 60000)]
    else:

        class DateClaim(BaseModel):
            issue_date: Evidenced[str]

        claims = [
            DateClaim(issue_date=Evidenced(value=v, evidence=[source]))
            for v in ("2026-03-04", "2026-04-03")
        ]
    assert all(verify(claim, document).fields[0].status == "needs_review" for claim in claims)


def test_flat_row_anchor_cannot_disambiguate_a_repeated_quantity() -> None:
    class Item(BaseModel):
        description: Evidenced[str]
        quantity: Evidenced[float]

    class Rows(BaseModel):
        items: list[Item]

    stream = io.BytesIO()
    pdf = Canvas(stream, invariant=True)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.drawString(40, 700, "Delivery")
    pdf.setFillColorRGB(0, 0, 0)
    pdf.drawString(200, 700, "2")
    pdf.drawString(40, 600, "Packing 2")
    pdf.save()
    data = Rows(
        items=[
            Item(
                description=Evidenced(value="Delivery", evidence=["Delivery"]),
                quantity=Evidenced(value=2, evidence=["2"]),
            )
        ]
    )
    report = verify(
        data,
        load_pdf(stream.getvalue()),
        row_rules=[RowEvidenceRule("items", "description", ("quantity",))],
    )
    assert all(field.status == "needs_review" for field in report.fields)
    assert "no strongly grounded" in report.fields[1].reasons[0]


def test_flat_headers_cannot_establish_table_column_roles() -> None:
    from test_column_evidence import specimen

    data, _ = specimen()
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=(612, 792), invariant=True)
    pdf.setFillColorRGB(1, 1, 1)
    for x, label in [(48, "Description"), (310, "Qty"), (400, "Unit price"), (510, "Amount")]:
        pdf.drawString(x, 700, label)
    pdf.setFillColorRGB(0, 0, 0)
    for x, value in zip((48, 310, 400, 510), ("Delivery-A", "3", "12.50", "37.50"), strict=True):
        pdf.drawString(x, 670, value)
    pdf.save()
    report = verify(data, load_pdf(stream.getvalue()))
    assert report.column_checks
    assert all(check.status == "unavailable" for check in report.column_checks)


def test_edit_tolerance_cannot_approve_flat_text() -> None:
    class Name(BaseModel):
        name: Evidenced[str]

    stream = io.BytesIO()
    pdf = Canvas(stream, invariant=True)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.drawString(40, 700, "Acme Services")
    pdf.save()
    result = verify(
        Name(name=Evidenced(value="Acme Service", evidence=["Acme Services"])),
        load_pdf(stream.getvalue()),
        text_edit_tolerance=2,
    ).fields[0]
    assert result.status == "needs_review"
    assert any("native-text paint contribution" in reason for reason in result.reasons)


@pytest.mark.parametrize("covered", [False, True])
def test_nested_reused_form_text_is_observed_without_editing_the_original(covered: bool) -> None:
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=(612, 792), invariant=True)
    pdf.beginForm("inner")
    pdf.setFont("Helvetica", 16)
    pdf.drawString(40, 600, "Authorized total: $900.00")
    pdf.endForm()
    pdf.beginForm("outer")
    pdf.doForm("inner")
    pdf.endForm()
    for shift in (0, -100):
        pdf.saveState()
        pdf.translate(0, shift)
        pdf.doForm("outer")
        pdf.restoreState()
    if covered:
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(30, 450, 550, 200, fill=1, stroke=0)
    pdf.save()
    content = stream.getvalue()
    document = load_pdf(content)
    expected = "no_contribution" if covered else "contributes"
    assert document.pages[0].words
    assert {w.raster_state for w in document.pages[0].words} == {expected}
    with (
        closing(pdfium.PdfDocument(content)) as original,
        closing(pdfium.PdfDocument(content)) as reference,
    ):
        page, disposable = original[0], reference[0]
        try:
            with _render_rgb(page, 16_000_000) as before:
                _suppress_text(disposable)
                with (
                    _render_rgb(disposable, 16_000_000) as suppressed,
                    ImageChops.difference(before, suppressed) as delta,
                ):
                    assert (delta.getbbox() is None) == covered
                with _render_rgb(page, 16_000_000) as after:
                    assert before.tobytes() == after.tobytes()
        finally:
            page.close()
            disposable.close()


def test_suppression_preserves_text_clipping_and_has_a_traversal_budget(monkeypatch) -> None:
    from fieldproof.document import raster_paint

    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=(612, 792), invariant=True)
    pdf.setFillAlpha(0)
    text = pdf.beginText(40, 600)
    text.setFont("Helvetica", 24)
    text.setTextRenderMode(4)  # Fill, then add the glyph outlines to the clip.
    text.textOut("Authorized total: $900.00")
    pdf.drawText(text)
    pdf.setFillAlpha(1)
    pdf.setFillColorRGB(0, 0, 1)
    pdf.rect(0, 0, 612, 792, fill=1, stroke=0)
    pdf.save()
    content = stream.getvalue()
    # The blue fill is retained in both renders: removing text paint must not
    # remove its clip and mistake subsequent path paint for native text paint.
    with (
        closing(pdfium.PdfDocument(content)) as original,
        closing(pdfium.PdfDocument(content)) as reference,
    ):
        page, disposable = original[0], reference[0]
        try:
            with _render_rgb(page, 16_000_000) as before:
                _suppress_text(disposable)
                with _render_rgb(disposable, 16_000_000) as after:
                    assert before.tobytes() == after.tobytes()
                    assert after.getextrema() != ((255, 255), (255, 255), (255, 255))
        finally:
            page.close()
            disposable.close()
    document = load_pdf(content)
    result = verify(
        Amount(total=Evidenced(value=900, evidence=["Authorized total: $900.00"])), document
    ).fields[0]
    assert result.status == "needs_review"
    monkeypatch.setattr(raster_paint, "MAX_PAGE_OBJECTS", 1)
    bounded = load_pdf(STUDY / "fixtures/black-on-white.pdf")
    assert {w.raster_state for w in bounded.pages[0].words} == {"unavailable"}
