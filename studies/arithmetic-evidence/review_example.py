"""Build the fictional invoice used to inspect arithmetic findings in the real review UI."""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    pdf = ROOT / "examples/line-arithmetic.pdf"
    canvas = Canvas(str(pdf), pagesize=(612, 792), invariant=True)
    canvas.setTitle("Synthetic invoice: a quoted line that does not multiply")
    canvas.setAuthor("Fieldproof synthetic example")
    canvas.setFillColor(HexColor("#14524c"))
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(48, 743, "SYNTHETIC DOCUMENT / LINE ARITHMETIC")
    canvas.setFillColor(HexColor("#182d2b"))
    canvas.setFont("Helvetica-Bold", 26)
    canvas.drawString(48, 694, "Example Workshop")
    canvas.setFont("Helvetica", 12)
    canvas.drawString(48, 655, "Invoice Number: FP-MATH")
    canvas.drawString(48, 629, "Issue Date: October 9, 2026")
    canvas.setStrokeColor(HexColor("#a6b7b3"))
    canvas.line(48, 595, 564, 595)
    canvas.setFont("Helvetica-Bold", 10)
    for x, text in [(48, "DESCRIPTION"), (319, "QTY"), (388, "UNIT PRICE"), (513, "AMOUNT")]:
        canvas.drawString(x, 567, text)
    canvas.setFont("Helvetica", 12)
    for x, text in [(48, "Precision bolts"), (325, "3"), (409, "19.95"), (529, "39.90")]:
        canvas.drawString(x, 532, text)
    canvas.line(48, 507, 564, 507)
    for y, label, value in [
        (465, "Subtotal", "39.90"),
        (437, "Tax", "3.19"),
        (397, "Total", "43.09"),
    ]:
        canvas.setFont("Helvetica-Bold" if label == "Total" else "Helvetica", 14)
        canvas.drawString(388, y, label)
        canvas.drawRightString(564, y, value)
    canvas.setFont("Helvetica", 11)
    canvas.setFillColor(HexColor("#415b56"))
    canvas.drawString(48, 302, "Every extracted number is printed on this page.")
    canvas.drawString(48, 279, "The line calculation still needs review: 3 x 19.95 is 59.85.")
    canvas.drawString(
        48, 256, "An adjustment could explain the difference; none is specified here."
    )
    canvas.setFont("Helvetica", 9)
    canvas.drawString(
        48, 62, "Deliberately inconsistent demonstration data. No real transaction or model output."
    )
    canvas.save()

    def e(value: str | float, quote: str) -> dict:
        return {"value": value, "evidence": [quote], "page": 1}

    quote = "Precision bolts 3 19.95 39.90"
    fixture = {
        "schema": "invoice",
        "provider": "fixture",
        "model": "synthetic line arithmetic",
        "data": {
            "vendor_name": e("Example Workshop", "Example Workshop"),
            "invoice_number": e("FP-MATH", "Invoice Number: FP-MATH"),
            "issue_date": e("2026-10-09", "Issue Date: October 9, 2026"),
            "line_items": [
                {
                    "description": e("Precision bolts", "Precision bolts"),
                    "quantity": e(3, quote),
                    "unit_price": e(19.95, quote),
                    "amount": e(39.9, quote),
                }
            ],
            "subtotal": e(39.9, "Subtotal 39.90"),
            "tax": e(3.19, "Tax 3.19"),
            "total": e(43.09, "Total 43.09"),
        },
    }
    (ROOT / "examples/fixtures/line-arithmetic.json").write_text(
        json.dumps(fixture, indent=2) + "\n"
    )
    print(f"Generated {pdf.relative_to(ROOT)} and its fixture")


if __name__ == "__main__":
    main()
