"""Build a synthetic example with a unique number borrowed from another item."""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    pdf = ROOT / "examples/row-association.pdf"
    canvas = Canvas(str(pdf), pagesize=(612, 792), invariant=True)
    canvas.setTitle("Synthetic invoice: unique quote, wrong item")
    canvas.setAuthor("Fieldproof synthetic example")
    canvas.setFillColor(HexColor("#14524c"))
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(48, 743, "SYNTHETIC DOCUMENT / ITEM ASSOCIATION")
    canvas.setFillColor(HexColor("#182d2b"))
    canvas.setFont("Helvetica-Bold", 26)
    canvas.drawString(48, 694, "Example Dispatch")
    canvas.setFont("Helvetica", 12)
    canvas.drawString(48, 655, "Invoice Number: FP-ASSOC")
    canvas.drawString(48, 629, "Issue Date: October 9, 2026")
    canvas.setStrokeColor(HexColor("#a6b7b3"))
    canvas.line(48, 595, 564, 595)
    canvas.setFont("Helvetica-Bold", 10)
    for x, text in [(48, "DESCRIPTION"), (380, "QTY"), (510, "AMOUNT")]:
        canvas.drawString(x, 567, text)
    canvas.setFont("Helvetica", 12)
    for y, label, qty, amount in [
        (532, "Delivery", "3", "90.00"),
        (501, "Packing", "2", "15.00"),
        (470, "Handling", "1", "5.00"),
    ]:
        for x, text in [(48, label), (385, qty), (515, amount)]:
            canvas.drawString(x, y, text)
    canvas.line(48, 444, 564, 444)
    for y, label, value in [
        (412, "Subtotal", "110.00"),
        (384, "Tax", "0.00"),
        (344, "Total", "110.00"),
    ]:
        canvas.setFont("Helvetica-Bold" if label == "Total" else "Helvetica", 14)
        canvas.drawString(380, y, label)
        canvas.drawRightString(564, y, value)
    canvas.setFillColor(HexColor("#415b56"))
    canvas.setFont("Helvetica", 11)
    canvas.drawString(
        48, 260, "Every quantity appears once. A unique quote can still name the wrong item."
    )
    canvas.drawString(48, 239, "The fixture borrows the middle row's quantity for the first line.")
    canvas.setFont("Helvetica", 9)
    canvas.drawString(
        48, 62, "Constructed demonstration data. No real transaction or model output."
    )
    canvas.save()

    def e(value: str | float, quote: str) -> dict:
        return {"value": value, "evidence": [quote], "page": 1}

    fixture = {
        "schema": "invoice",
        "provider": "fixture",
        "model": "synthetic item association",
        "data": {
            "vendor_name": e("Example Dispatch", "Example Dispatch"),
            "invoice_number": e("FP-ASSOC", "Invoice Number: FP-ASSOC"),
            "issue_date": e("2026-10-09", "Issue Date: October 9, 2026"),
            "line_items": [
                {
                    "description": e(label, label),
                    "quantity": e(qty, str(qty)),
                    "amount": e(amount, quote),
                }
                for label, qty, amount, quote in [
                    ("Delivery", 2, 90, "Delivery 3 90.00"),
                    ("Packing", 2, 15, "Packing 2 15.00"),
                    ("Handling", 1, 5, "Handling 1 5.00"),
                ]
            ],
            "subtotal": e(110, "Subtotal 110.00"),
            "tax": e(0, "Tax 0.00"),
            "total": e(110, "Total 110.00"),
        },
    }
    (ROOT / "examples/fixtures/row-association.json").write_text(
        json.dumps(fixture, indent=2) + "\n"
    )
    print(f"Generated {pdf.relative_to(ROOT)} and its fixture")


if __name__ == "__main__":
    main()
