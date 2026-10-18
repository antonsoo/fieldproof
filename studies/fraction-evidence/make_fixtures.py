"""Generate authored fraction evidence with an embedded DejaVu Sans subset.

Use --font /path/to/DejaVuSans.ttf. The font license is retained in the
neighboring arabic-numbers study; these are controlled documents, not invoices
from an actual transaction.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

HERE = Path(__file__).resolve().parent


def generate(font):
    pdfmetrics.registerFont(TTFont("FractionEvidence", str(font)))
    destination = HERE / "fixtures"
    cases = [
        {"slash": slash, "gap": gap, "text": f"Cut length 1{gap}{slash}{gap}2 m"}
        for gap in ("", " ")
        for slash in ("/", "⁄", "∕")
    ]
    canvas = Canvas(str(destination / "fractions.pdf"), invariant=True)
    canvas.setTitle("Authored fraction evidence controls")
    canvas.setAuthor("Anton Soloviev")
    for case in cases:
        canvas.setFont("FractionEvidence", 14)
        canvas.drawString(48, 700, case["text"])
        canvas.showPage()
    canvas.save()
    (destination / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n")
    canvas = Canvas(str(destination / "review.pdf"), invariant=True)
    canvas.setTitle("Authored fractional cut-length invoice")
    canvas.setAuthor("Anton Soloviev")
    canvas.setFont("FractionEvidence", 18)
    canvas.drawString(48, 740, "Workshop Supply")
    canvas.setFont("FractionEvidence", 12)
    for y, text in [
        (705, "Invoice: FRAC-2026-18"),
        (680, "Issued: 2026-10-18"),
        (550, "Total USD 9.00"),
        (480, "Authored document. No actual transaction or model evaluation."),
    ]:
        canvas.drawString(48, y, text)
    canvas.drawString(48, 630, "Cable cut to length")
    canvas.drawString(310, 630, "Quantity 1⁄2 m")
    canvas.drawString(475, 630, "9.00")
    canvas.save()
    data = {
        "vendor_name": {"value": "Workshop Supply", "evidence": ["Workshop Supply"]},
        "invoice_number": {"value": "FRAC-2026-18", "evidence": ["FRAC-2026-18"]},
        "issue_date": {"value": "2026-10-18", "evidence": ["2026-10-18"]},
        "line_items": [
            {
                "description": {
                    "value": "Cable cut to length",
                    "evidence": ["Cable cut to length"],
                },
                "quantity": {"value": 1, "evidence": ["Quantity 1⁄2 m"]},
                "amount": {"value": 9, "evidence": ["Cable cut to length Quantity 1⁄2 m 9.00"]},
            }
        ],
        "total": {"value": 9, "evidence": ["Total USD 9.00"]},
    }
    (destination / "review.json").write_text(
        json.dumps({"schema": "invoice", "data": data}, ensure_ascii=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, required=True)
    generate(parser.parse_args().font)
