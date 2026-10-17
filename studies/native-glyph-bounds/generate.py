"""Author ordinary-font overhang controls and exact omitted-nine counterparts.

These PDFs are synthetic visibility experiments, not receipts from transactions.
The author covers the original nine independently of either PDF text parser.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from reportlab.pdfbase.pdfdoc import PDFDictionary, PDFResourceDictionary
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

HERE = Path(__file__).resolve().parent
QUOTE = "Authorized total: $900.00"
PREFIX = "Authorized total: $"
X, Y, SIZE = 48, 550, 16

CASES = [
    *(
        {"id": f"{font}-{size}-{top}", "font": font, "size": size, "top": top, "hidden": True}
        for font in ("Helvetica-Oblique", "Helvetica-BoldOblique")
        for size, top in ((16, 4), (16, 8), (20, 4), (20, 8), (30, 4))
    ),
    *(
        {
            "id": f"Times-Italic-{size}-{top}",
            "font": "Times-Italic",
            "size": size,
            "top": top,
            "hidden": True,
        }
        for size in (20, 30)
        for top in (4, 8)
    ),
    *(
        {"id": f"rotation-{rotation}", "rotation": rotation, "hidden": True}
        for rotation in (90, 180, 270)
    ),
    {"id": "cropped-overhang", "crop": True, "hidden": True},
    {"id": "nested-form", "form": True, "hidden": True},
    {"id": "scaled-form", "form": True, "scaled": True, "hidden": True},
    *(
        {"id": f"stroked-overhang-{join}", "stroke": 12, "join": join, "hidden": True}
        for join in (0, 1, 2)
    ),
    {"id": "visible-plain", "lender": False},
    {"id": "visible-italic", "lender": False, "source_font": "Helvetica-Oblique"},
    {"id": "visible-small", "lender": False, "source_size": 8},
    {
        "id": "visible-small-italic",
        "lender": False,
        "source_size": 8,
        "source_font": "Helvetica-Oblique",
    },
    {"id": "invisible-lender", "lender_mode": 3},
    {"id": "transparent-lender", "lender_alpha": 0},
    {"id": "nearby-lender", "nearby": True},
    {"id": "nearby-miter-stroke", "nearby": True, "stroke": 12, "review": True},
    {"id": "nearby-round-stroke", "nearby": True, "stroke": 12, "join": 1},
    {"id": "far-miter-stroke", "nearby": True, "offset": 200, "stroke": 12},
    {
        "id": "larger-miter-limit",
        "hidden": True,
        "stroke": 12,
        "miter": 30,
        "miter_gs": True,
        "form": True,
    },
    {
        "id": "unreadable-miter-limit",
        "nearby": True,
        "offset": 200,
        "stroke": 12,
        "miter": "unknown",
        "review": True,
    },
    {
        "id": "scaled-round-stroke",
        "hidden": True,
        "stroke": 12,
        "join": 1,
        "form": True,
        "scaled": True,
        "scale_x": 1.3,
        "scale_y": 0.8,
    },
]


def draw_case(case: dict, *, omit_nine: bool = False) -> bytes:
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=(612, 792), invariant=True, pageCompression=1)
    pdf.setTitle("Synthetic invoice: native glyph overhang")
    pdf.setAuthor("Fieldproof fixture generator")
    if case.get("rotation"):
        pdf.setPageRotation(case["rotation"])
    if case.get("crop"):
        pdf.setCropBox((0, 545, 612, 792))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(48, 724, "SYNTHETIC INVOICE")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(48, 680, "Example Tools Ltd.")
    pdf.drawString(48, 656, "Invoice OVERHANG-001")
    pdf.drawString(48, 632, "Issued: 2026-10-17")
    pdf.drawString(48, 480, "Authored font-ink control; no real transaction.")
    pdf.setFont("Helvetica", 8)
    pdf.drawString(48, 456, "Visible small print: Visa, services, lilies and days' notices.")
    if case.get("form"):
        pdf.beginForm("inner")
    source_font, source_size = case.get("source_font", "Helvetica"), case.get("source_size", SIZE)
    pdf.setFont(source_font, source_size)
    x_digit = X + stringWidth(PREFIX, source_font, source_size)
    digit_width = stringWidth("9", source_font, source_size)
    if omit_nine:
        pdf.drawString(X, Y, PREFIX)
        pdf.drawString(x_digit + digit_width, Y, "00.00")
    else:
        pdf.drawString(X, Y, QUOTE)
    if case.get("hidden"):
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(x_digit - 0.05, Y - 3, digit_width + 0.1, 20, fill=1, stroke=0)
    if case.get("lender", True):
        pdf.saveState()
        font, size = case.get("font", "Helvetica-Oblique"), case.get("size", 16)
        pdf.setFillColorRGB(0, 0, 0)
        pdf.setStrokeColorRGB(0, 0, 0)
        pdf.setFillAlpha(case.get("lender_alpha", 1))
        pdf.setLineWidth(case.get("stroke", 1))
        pdf.setLineJoin(case.get("join", 0))
        if case.get("miter_gs"):
            original_state = pdf._extgstate.getState

            def state_with_miter():
                state = original_state()
                values = dict(state.dict) if state is not None else {}
                values["MiterGS"] = PDFDictionary({"ML": case["miter"]})
                return PDFDictionary(values)

            pdf._extgstate.getState = state_with_miter
            pdf._code.append("/MiterGS gs")
        elif case.get("miter") == "unknown":
            pdf._code.append("/Unknown M")
        elif "miter" in case:
            pdf.setMiterLimit(case["miter"])
        # Its advance ends BEFORE the nine's layout box. Only the italic
        # outline/edge, or a stroke, can extend into that otherwise blank box.
        x = x_digit - stringWidth("7", font, size) - 0.75
        y = Y + case.get("top", 4) - size * 0.69
        if case.get("nearby"):
            y -= case.get("offset", 60)
        text = pdf.beginText(x, y)
        text.setFont(font, size)
        text.setTextRenderMode(case.get("lender_mode", 1 if case.get("stroke") else 0))
        text.textOut("7")
        pdf.drawText(text)
        pdf.restoreState()
    if case.get("form"):
        # ReportLab's Form formatter does not copy its ExtGState attribute into
        # the resource dictionary. Declare the invoked state's actual resource
        # explicitly; an unresolved /MiterGS would not exercise an ML of 30.
        resources = PDFResourceDictionary()
        resources.basicFonts()
        resources.basicProcs()
        if case.get("miter_gs"):
            resources.ExtGState = PDFDictionary({"MiterGS": PDFDictionary({"ML": case["miter"]})})
        pdf.endForm(Resources=resources)
        pdf.beginForm("outer")
        if case.get("scaled"):
            pdf.translate(30, 70)
            pdf.scale(case.get("scale_x", 0.8), case.get("scale_y", 0.8))
        pdf.doForm("inner")
        pdf.endForm()
        pdf.doForm("outer")
    pdf.save()
    return stream.getvalue()


def main() -> None:
    (HERE / "fixtures").mkdir(parents=True, exist_ok=True)
    for case in CASES:
        (HERE / "fixtures" / f"{case['id']}.pdf").write_bytes(draw_case(case))
    (HERE / "cases.json").write_text(json.dumps(CASES, indent=2) + "\n")
    data = {
        "vendor_name": {"value": "Example Tools Ltd.", "evidence": ["Example Tools Ltd."]},
        "invoice_number": {"value": "OVERHANG-001", "evidence": ["Invoice OVERHANG-001"]},
        "issue_date": {"value": "2026-10-17", "evidence": ["Issued: 2026-10-17"]},
        "total": {"value": 900, "evidence": [QUOTE]},
    }
    payload = {"schema": "invoice", "data": data}
    (HERE / "fixture.json").write_text(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
