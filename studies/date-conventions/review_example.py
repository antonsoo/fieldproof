"""Generate the constructed date-reference PDF and handwritten extraction fixture."""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    path = ROOT / "examples/date-convention.pdf"
    canvas = Canvas(str(path), pagesize=(612, 792), invariant=True)
    canvas.setTitle("Synthetic date-convention evidence")
    canvas.setAuthor("Fieldproof synthetic example")
    canvas.setFillColor(HexColor("#14524c"))
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(48, 742, "SYNTHETIC DOCUMENT / DATE EVIDENCE")
    canvas.setFillColor(HexColor("#182d2b"))
    canvas.setFont("Helvetica-Bold", 26)
    canvas.drawString(48, 690, "Example Workshop")
    canvas.setFont("Helvetica", 12)
    canvas.drawString(48, 645, "Invoice Number: FP-DATE")
    canvas.drawString(48, 610, "Issue Date: 03/04/2026")
    canvas.drawString(48, 575, "Reference: 99/01/2026")
    canvas.setStrokeColor(HexColor("#a6b7b3"))
    canvas.line(48, 545, 564, 545)
    canvas.setFont("Helvetica-Bold", 18)
    canvas.drawString(48, 500, "Total")
    canvas.drawRightString(564, 500, "$100.00")
    canvas.setFont("Helvetica", 10)
    canvas.setFillColor(HexColor("#415b56"))
    canvas.drawString(48, 450, "The reference is not a valid calendar date.")
    canvas.drawString(
        48, 430, "It cannot establish whether the issue date is day-first or month-first."
    )
    canvas.drawString(
        48, 70, "Hand-written demonstration data. No real transaction or model output."
    )
    canvas.save()

    def evidenced(value: str | float, quote: str) -> dict:
        return {"value": value, "evidence": [quote], "page": 1}

    fixture = {
        "schema": "Invoice",
        "provider": "fixture",
        "model": "synthetic ambiguous-date claim",
        "data": {
            "vendor_name": evidenced("Example Workshop", "Example Workshop"),
            "invoice_number": evidenced("FP-DATE", "Invoice Number: FP-DATE"),
            "issue_date": evidenced("2026-04-03", "Issue Date: 03/04/2026"),
            "total": evidenced(100.0, "$100.00"),
        },
    }
    (ROOT / "examples/fixtures/date-convention.json").write_text(
        json.dumps(fixture, indent=2) + "\n"
    )
    print("Generated examples/date-convention.pdf and its extraction fixture")


if __name__ == "__main__":
    main()
