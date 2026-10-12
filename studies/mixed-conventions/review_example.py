"""Build the illustrative synthetic PDF and handwritten extraction fixture."""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    canvas = Canvas(
        str(ROOT / "examples/mixed-conventions.pdf"), pagesize=(612, 792), invariant=True
    )
    canvas.setTitle("Synthetic mixed-convention evidence")
    canvas.setAuthor("Fieldproof synthetic example")
    canvas.setFillColor(HexColor("#14524c"))
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(48, 742, "SYNTHETIC DOCUMENT / MIXED CONVENTIONS")
    canvas.setFillColor(HexColor("#182d2b"))
    canvas.setFont("Helvetica-Bold", 26)
    canvas.drawString(48, 690, "Example Workshop")
    canvas.setFont("Helvetica", 12)
    canvas.drawString(48, 645, "Invoice Number: FP-MIXED")
    canvas.drawString(48, 610, "Issue Date: 03/04/2026")
    canvas.setFont("Helvetica-Bold", 18)
    canvas.drawString(48, 565, "Total")
    canvas.drawRightString(564, 565, "60.000")
    canvas.setStrokeColor(HexColor("#a6b7b3"))
    canvas.line(48, 530, 564, 530)
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(48, 490, "Other quoted formats")
    canvas.setFont("Helvetica", 12)
    canvas.drawString(48, 455, "US appendix: 1,234.50 on 12/31/2026")
    canvas.drawString(48, 420, "European appendix: 1.234,50 on 31/12/2026")
    canvas.setFont("Helvetica", 10)
    canvas.setFillColor(HexColor("#415b56"))
    canvas.drawString(48, 360, "Both conventions occur in this constructed document.")
    canvas.drawString(
        48, 340, "A document-wide fallback cannot establish the total or issue-date reading."
    )
    canvas.drawString(
        48, 70, "Handwritten demonstration data. No real transaction or model output."
    )
    canvas.save()

    def evidenced(value: str | float, quote: str) -> dict:
        return {"value": value, "evidence": [quote], "page": 1}

    fixture = {
        "schema": "Invoice",
        "provider": "fixture",
        "model": "synthetic ambiguous amount and date",
        "data": {
            "vendor_name": evidenced("Example Workshop", "Example Workshop"),
            "invoice_number": evidenced("FP-MIXED", "Invoice Number: FP-MIXED"),
            "issue_date": evidenced("2026-04-03", "Issue Date: 03/04/2026"),
            "total": evidenced(60000.0, "60.000"),
        },
    }
    (ROOT / "examples/fixtures/mixed-conventions.json").write_text(
        json.dumps(fixture, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
