"""Author clipping controls with known geometry; no extraction model is involved."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pypdfium2 as pdfium
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase.pdfdoc import PDFArray

ROOT = Path(__file__).resolve().parent
ALTERNATE = "Authorized total: $900.00"
VISIBLE = "Visible total: $90.00"


def text(pdf, value, y=600):
    pdf.setFont("Helvetica", 16)
    pdf.drawString(40, y, value)


def draw_case(case, omit_alternate=False):
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=(612, 792), invariant=True)
    text(pdf, VISIBLE, 700)
    pdf.saveState()
    kind = case.get("kind", "path")
    if kind == "form":
        if case.get("inherited"):
            pdf._code.append("0 0 300 300 re W n")
        # A Form clips to its BBox even without an explicit W operator.
        bounds = (0, 0, 612, 792) if case.get("inside") else (0, 0, 300, 300)
        pdf.beginForm("alternate", *bounds)
        if case.get("nested"):
            pdf.beginForm("inner", 0, 0, 612, 792)
        if not omit_alternate:
            text(pdf, ALTERNATE)
        if case.get("nested"):
            pdf.endForm()
            pdf.doForm("inner")
        pdf.endForm()
        if case.get("form_matrix"):
            form = pdf._doc.idToObject[pdf._doc.getXObjectName("alternate")]
            form.Matrix = PDFArray(case["form_matrix"])
        if case.get("matrix"):
            # Place the form on the page; the clip must use the same transform.
            pdf.transform(*case["matrix"])
        pdf.doForm("alternate")
    else:
        if case.get("matrix"):
            pdf.transform(*case["matrix"])
        if case.get("restore"):
            pdf.saveState()
        if case.get("paint_only"):
            pdf._code.append("0 0 300 300 re S")
        if case.get("prior"):
            pdf._code.append(case["prior"] + " W n")
        if case.get("path") is not None:
            pdf._code.append(case["path"])
            pdf._code.append(case.get("clip", "W") + " " + case.get("end", "n"))
        if case.get("restore"):
            pdf.restoreState()
        if case.get("post_matrix"):
            pdf.transform(*case["post_matrix"])
        if not omit_alternate:
            text(pdf, ALTERNATE)
    pdf.restoreState()
    text(pdf, "Footer control", 450)
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
    cases = [{"id": "ordinary", "hidden": False}]
    for operator in ("n", "S", "s", "f", "F", "f*", "B", "B*", "b", "b*"):
        cases.append({"id": "end-" + operator.replace("*", "-star"),
                      "path": "0 0 300 300 re", "end": operator, "hidden": True})
    cases += [
        {"id": "even-odd", "path": "0 0 300 300 re", "clip": "W*", "hidden": True},
        {"id": "no-current-path", "path": "", "hidden": False},
        {"id": "degenerate", "path": "40 600 0 0 re", "hidden": True},
        {"id": "negative-size", "path": "300 300 -300 -300 re", "hidden": True},
        {"id": "inside", "path": "0 500 500 200 re", "hidden": False},
        {"id": "restore", "path": "0 0 300 300 re", "restore": True, "hidden": False},
        {"id": "intersection-empty", "prior": "0 0 300 300 re",
         "path": "0 500 500 200 re", "hidden": True},
        {"id": "intersection-inside", "prior": "0 400 600 392 re",
         "path": "0 500 500 200 re", "hidden": False},
        {"id": "triangle", "path": "0 0 m 300 0 l 0 300 l h", "hidden": True},
        {"id": "cubic", "path": "0 0 m 100 200 200 100 300 0 c h", "hidden": True},
        {"id": "curve-v", "path": "0 0 m 200 200 300 0 v h", "hidden": True},
        {"id": "curve-y", "path": "0 0 m 200 200 300 0 y h", "hidden": True},
        {"id": "compound-inside", "path": "0 500 500 200 re 0 0 300 300 re",
         "hidden": False},
        {"id": "partial", "path": "0 500 205 200 re", "hidden": False, "review": True},
        {"id": "transformed-hidden", "path": "0 0 300 300 re",
         "matrix": [0.75, 0, 0, 0.75, 50, 30], "hidden": True},
        {"id": "transformed-inside", "path": "0 500 500 200 re",
         "matrix": [0.75, 0, 0, 0.75, 50, 30], "hidden": False},
        {"id": "form-bbox", "kind": "form", "hidden": True},
        {"id": "form-inside", "kind": "form", "inside": True, "hidden": False},
        {"id": "form-inherited", "kind": "form", "inside": True,
         "inherited": True, "hidden": True},
        {"id": "form-nested", "kind": "form", "nested": True, "hidden": True},
        {"id": "form-matrix", "kind": "form",
         "matrix": [0.75, 0, 0, 0.75, 50, 30], "hidden": True},
        {"id": "form-matrix-inside", "kind": "form", "inside": True,
         "matrix": [0.75, 0, 0, 0.75, 50, 30], "hidden": False},
        {"id": "form-dictionary-matrix", "kind": "form",
         "form_matrix": [0.75, 0, 0, 0.75, 50, 30], "hidden": True},
        {"id": "form-dictionary-matrix-inside", "kind": "form", "inside": True,
         "form_matrix": [0.75, 0, 0, 0.75, 50, 30], "hidden": False},
        {"id": "content-rotation", "path": "0 0 300 300 re",
         "matrix": [0, 0.7, -0.7, 0, 480, 60], "hidden": True},
        {"id": "content-rotation-inside", "path": "0 500 500 200 re",
         "matrix": [0, 0.7, -0.7, 0, 480, 60], "hidden": False},
        {"id": "post-transform-hidden", "path": "0 500 500 200 re",
         "post_matrix": [0.5, 0, 0, 0.5, 0, 0], "hidden": True},
        {"id": "post-transform-inside", "path": "0 0 300 300 re",
         "post_matrix": [1, 0, 0, 1, 0, -400], "hidden": False},
        {"id": "paint-only", "paint_only": True, "hidden": False},
        {"id": "paint-path-reset", "paint_only": True,
         "path": "0 500 500 200 re", "hidden": False},
        {"id": "form-dictionary-rotation", "kind": "form",
         "form_matrix": [0, 0.7, -0.7, 0, 480, 60], "hidden": True},
        {"id": "form-dictionary-rotation-inside", "kind": "form", "inside": True,
         "form_matrix": [0, 0.7, -0.7, 0, 480, 60], "hidden": False},
    ]
    cases += [{"id": f"rotated-{angle}", "rotation": angle,
               "path": "0 0 300 300 re", "hidden": True} for angle in (90, 180, 270)]
    directory = ROOT / "fixtures"
    directory.mkdir(parents=True, exist_ok=True)
    for case in cases:
        case["review"] = case.get("review", case["hidden"])
        (directory / f"{case['id']}.pdf").write_bytes(draw_case(case))
    (ROOT / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")
    data = {
        "vendor_name": {"value": "Example", "evidence": []},
        "invoice_number": {"value": "CLIP-0", "evidence": []},
        "issue_date": {"value": "2026-10-15", "evidence": []},
        "total": {"value": 900, "evidence": [ALTERNATE], "page": 1},
    }
    (ROOT / "fixture.json").write_text(json.dumps(data, indent=2) + "\n")
    (ROOT / "extraction.json").write_text(json.dumps({"schema": "invoice", "data": data}, indent=2) + "\n")
    return cases


if __name__ == "__main__":
    print(f"Generated {len(generate())} authored clipping controls")
