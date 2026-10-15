"""Author PDF transparency controls with explicit expectations, without model calls."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pypdfium2 as pdfium
from reportlab.pdfbase import pdfdoc
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parent
ALTERNATE = "Authorized total: $900.00"
VISIBLE = "Visible total: $90.00"


def text(pdf, value, y=600, mode=None):
    item = pdf.beginText(40, y)
    item.setFont("Helvetica", 16)
    if mode is not None:
        item.setTextRenderMode(mode)
    item.textLine(value)
    pdf.drawText(item)


def end_form(pdf, name, group=False):
    pdf.endForm()
    form = pdf._doc.idToObject[pdf._doc.getXObjectName(name)]
    # ReportLab's default Form formatter does not copy ExtGState into Resources.
    # Include it explicitly so an alpha command INSIDE a form is valid PDF.
    resources = pdfdoc.PDFResourceDictionary()
    resources.basicFonts()
    resources.ExtGState = form.ExtGState
    if form.XObjects:
        resources.XObject = form.XObjects
    form.Resources = resources
    if group:
        form.Contents = pdfdoc.PDFStream(pdfdoc.PDFDictionary({
            "Group": pdfdoc.PDFDictionary({"S": pdfdoc.PDFName("Transparency"), "I": True}),
        }), form.stream)


def draw_case(case, omit_alternate=False):
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=(612, 792), invariant=True)
    text(pdf, VISIBLE, 680, mode=0)
    pdf.saveState()
    fill, stroke = case.get("fill", 1), case.get("stroke", 1)
    kind, mode = case.get("kind", "direct"), case.get("mode", 0)
    if kind in ("form-internal", "form-override", "nested", "group-override"):
        pdf.beginForm("alternate")
        pdf.setFillAlpha(0)
        pdf.setStrokeAlpha(0)
        if kind in ("form-override", "group-override"):
            # Emit an explicit reset; ReportLab omits setAlpha(1) in its default state.
            pdf.setFillAlpha(1)
            pdf.setStrokeAlpha(1)
        if kind == "nested":
            pdf.beginForm("inner")
        if not omit_alternate:
            text(pdf, ALTERNATE, mode=mode)
        if kind == "nested":
            end_form(pdf, "inner")
            pdf.doForm("inner")
        end_form(pdf, "alternate", group=kind == "group-override")
        pdf.setFillAlpha(fill)
        pdf.setStrokeAlpha(stroke)
        pdf.doForm("alternate")
    elif kind in ("form-inherited", "group-inherited", "inherited-mode"):
        pdf.beginForm("alternate")
        if not omit_alternate:
            text(pdf, ALTERNATE, mode=None if kind == "inherited-mode" else mode)
        end_form(pdf, "alternate", group=kind == "group-inherited")
        pdf.setFillAlpha(fill)
        pdf.setStrokeAlpha(stroke)
        if kind == "inherited-mode":
            pdf._code.append(f"{mode} Tr")
        pdf.doForm("alternate")
    elif kind == "restore":
        pdf.setFillAlpha(1)
        pdf.saveState()
        pdf.setFillAlpha(0)
        pdf.saveState()
        pdf.setFillAlpha(0.5)
        pdf.restoreState()
        pdf.restoreState()
        if not omit_alternate:
            text(pdf, ALTERNATE, mode=mode)
    else:
        pdf.setFillAlpha(fill)
        pdf.setStrokeAlpha(stroke)
        if not omit_alternate:
            text(pdf, ALTERNATE, mode=mode)
    pdf.restoreState()
    text(pdf, "Footer control", 500, mode=0)
    pdf.save()
    content = stream.getvalue()
    if case.get("rotation"):
        with pdfium.PdfDocument(content) as document:
            page = document[0]
            page.set_rotation(case["rotation"])
            output = io.BytesIO()
            document.save(output)
            page.close()
            content = output.getvalue()
    return content


def generate():
    directory = ROOT / "fixtures"
    directory.mkdir(parents=True, exist_ok=True)
    cases = []
    for mode in (0, 1, 2, 4, 5, 6):
        for fill, stroke in ((0, 1), (1, 0), (0, 0), (1, 1), (0.5, 0.5)):
            painted = (mode % 4 in (0, 2) and fill > 0) or (mode % 4 in (1, 2) and stroke > 0)
            cases.append({"id": f"mode-{mode}-fill-{fill}-stroke-{stroke}", "mode": mode,
                          "fill": fill, "stroke": stroke, "hidden": not painted})
    cases += [
        {"id": "form-inherited", "kind": "form-inherited", "fill": 0, "hidden": True},
        {"id": "form-internal", "kind": "form-internal", "hidden": True},
        {"id": "form-override", "kind": "form-override", "fill": 0, "hidden": False},
        {"id": "nested", "kind": "nested", "hidden": True},
        {"id": "restore", "kind": "restore", "hidden": False},
        {"id": "group-inherited", "kind": "group-inherited", "fill": 0,
         "mode": 1, "hidden": True},
        {"id": "group-reset", "kind": "group-inherited", "fill": 1,
         "stroke": 0, "mode": 1, "hidden": False},
        {"id": "group-override", "kind": "group-override", "fill": 0, "hidden": True},
        {"id": "inherited-mode", "kind": "inherited-mode", "mode": 3, "hidden": True},
    ]
    cases += [{"id": f"rotated-{angle}", "rotation": angle, "fill": 0, "hidden": True}
              for angle in (90, 180, 270)]
    for case in cases:
        (directory / f"{case['id']}.pdf").write_bytes(draw_case(case))
    (ROOT / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")
    data = {
        "vendor_name": {"value": "Example", "evidence": []},
        "invoice_number": {"value": "ALPHA-0", "evidence": []},
        "issue_date": {"value": "2026-10-15", "evidence": []},
        "total": {"value": 900, "evidence": [ALTERNATE], "page": 1},
    }
    (ROOT / "fixture.json").write_text(json.dumps(data, indent=2) + "\n")
    (ROOT / "extraction.json").write_text(json.dumps({"schema": "invoice", "data": data}, indent=2) + "\n")
    return cases


if __name__ == "__main__":
    print(f"Generated {len(generate())} authored PDF controls")
