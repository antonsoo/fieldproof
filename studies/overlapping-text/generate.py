"""Author synthetic PDFs with a hidden nine and a separately painted one.

The omitted-digit controls preserve every other glyph's coordinates. No PDF
parser or Fieldproof observation is used to decide what the author paints.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

HERE = Path(__file__).resolve().parent
QUOTE = "Authorized total: $900.00"
PREFIX = "Authorized total: $"
X, Y, SIZE = 48, 550, 16

CASES = [
    *({"id": f"replacement-{size}", "size": size, "review": True}
      for size in (10, 15, 17, 20)),
    *({"id": f"rotation-{rotation}", "size": 15, "rotation": rotation, "review": True}
      for rotation in (90, 180, 270)),
    {"id": "cropped-lender", "size": 20, "crop": True, "review": True},
    {"id": "nested-form", "size": 15, "form": True, "review": True},
    {"id": "visible-original", "size": None, "review": False},
    {"id": "invisible-lender", "size": 15, "lender_mode": 3, "review": False},
    {"id": "transparent-lender", "size": 15, "lender_alpha": 0, "review": False},
    {"id": "nearby-lender", "size": 15, "nearby": True, "review": False},
    {"id": "visible-kerning", "size": None, "kern": True, "review": False},
]


def draw_case(case: dict, *, omit_nine: bool = False) -> bytes:
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=(612, 792), invariant=True, pageCompression=1)
    pdf.setTitle("Synthetic invoice: overlapping native text")
    pdf.setAuthor("Fieldproof fixture generator")
    if case.get("rotation"):
        pdf.setPageRotation(case["rotation"])
    if case.get("crop"):
        # The old 16-point glyph fits; the lender's 20-point bounds cross the
        # view boundary. A discarded character can still paint visible pixels.
        pdf.setCropBox((0, 0, 612, Y + 14))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(48, 724, "SYNTHETIC INVOICE")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(48, 680, "Example Tools Ltd.")
    pdf.drawString(48, 656, "Invoice OVERLAP-001")
    pdf.drawString(48, 632, "Issued: 2026-10-17")
    pdf.drawString(48, 480, "Authored visibility counterexample; no real transaction.")
    if case.get("kern"):
        kerned = pdf.beginText(48, 590)
        kerned.setFont("Helvetica", 16)
        kerned.setCharSpace(-0.5)
        kerned.textOut("AVATAR WATER")
        pdf.drawText(kerned)
    if case.get("form"):
        pdf.beginForm("inner")
    pdf.setFont("Helvetica", SIZE)
    x_digit = X + stringWidth(PREFIX, "Helvetica", SIZE)
    digit_width = stringWidth("9", "Helvetica", SIZE)
    if omit_nine:
        pdf.drawString(X, Y, PREFIX)
        pdf.drawString(x_digit + digit_width, Y, "00.00")
    else:
        pdf.drawString(X, Y, QUOTE)
    replacement = case["size"]
    hidden = case["review"]
    if hidden:
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(x_digit - 0.05, Y - 3, digit_width + 0.1, 20, fill=1, stroke=0)
    if replacement is not None:
        pdf.saveState()
        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFillAlpha(case.get("lender_alpha", 1))
        text = pdf.beginText(x_digit, Y - 40 if case.get("nearby") else Y)
        text.setFont("Helvetica", replacement)
        text.setTextRenderMode(case.get("lender_mode", 0))
        text.textOut("1")
        pdf.drawText(text)
        pdf.restoreState()
    if case.get("form"):
        pdf.endForm()
        pdf.beginForm("outer")
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
        "invoice_number": {"value": "OVERLAP-001", "evidence": ["Invoice OVERLAP-001"]},
        "issue_date": {"value": "2026-10-17", "evidence": ["Issued: 2026-10-17"]},
        "total": {"value": 900, "evidence": [QUOTE]},
    }
    (HERE / "fixture.json").write_text(json.dumps({"schema": "invoice", "data": data}, indent=2) + "\n")


if __name__ == "__main__":
    main()
