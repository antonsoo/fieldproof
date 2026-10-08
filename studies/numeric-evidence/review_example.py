"""Generate the synthetic signed-amount PDF and its deliberately wrong extraction.

    uv run --locked python studies/numeric-evidence/review_example.py

No model or network is involved. The fixture quotes the printed amount while
omitting its minus sign, then claims a positive total.
"""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    pdf = ROOT / "examples/signed-amount.pdf"
    canvas = Canvas(str(pdf), pagesize=(612, 792), invariant=True)
    canvas.setTitle("Synthetic signed-amount evidence")
    canvas.setAuthor("Fieldproof synthetic example")
    canvas.setFillColor(HexColor("#14524c"))
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(48, 742, "SYNTHETIC DOCUMENT / NUMERIC EVIDENCE")
    canvas.setFillColor(HexColor("#182d2b"))
    canvas.setFont("Helvetica-Bold", 26)
    canvas.drawString(48, 690, "Example Workshop")
    canvas.setFont("Helvetica", 12)
    canvas.drawString(48, 655, "Credit note")
    canvas.drawString(48, 613, "Invoice Number: FP-SIGN")
    canvas.drawString(48, 588, "Issue Date: October 8, 2026")
    canvas.setStrokeColor(HexColor("#a6b7b3"))
    canvas.line(48, 556, 564, 556)
    canvas.setFont("Helvetica", 12)
    canvas.drawString(48, 520, "Returned shipment")
    canvas.setFont("Helvetica-Bold", 18)
    canvas.drawString(48, 470, "Total")
    canvas.drawRightString(564, 470, "- $100.00")
    canvas.line(48, 445, 564, 445)
    canvas.setFont("Helvetica", 10)
    canvas.setFillColor(HexColor("#415b56"))
    canvas.drawString(48, 405, "The minus sign is part of the amount. This is a credit.")
    canvas.drawString(48, 385, "A positive extraction of the total must be sent to review.")
    canvas.drawString(
        48, 70, "Hand-written demonstration data. No real transaction or model output."
    )
    canvas.save()

    def evidence(value: str | float, quote: str) -> dict:
        return {"value": value, "evidence": [quote], "page": 1}

    fixture = {
        "schema": "Invoice",
        "provider": "fixture",
        "model": "synthetic numeric-evidence fixture (deliberately omitted minus sign)",
        "data": {
            "vendor_name": evidence("Example Workshop", "Example Workshop"),
            "invoice_number": evidence("FP-SIGN", "Invoice Number: FP-SIGN"),
            "issue_date": evidence("2026-10-08", "Issue Date: October 8, 2026"),
            "total": evidence(100.0, "$100.00"),
        },
    }
    path = ROOT / "examples/fixtures/signed-amount.json"
    path.write_text(json.dumps(fixture, indent=2) + "\n")
    print(f"Generated {pdf.relative_to(ROOT)} and {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
