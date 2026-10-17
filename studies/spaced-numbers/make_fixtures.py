"""Author controlled grouping and column PDFs; font license is in ../arabic-numbers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", required=True, type=Path)
    args = parser.parse_args()
    pdfmetrics.registerFont(TTFont("SpaceNumbers", str(args.font)))
    cases = json.loads((HERE / "intl.json").read_text())["cases"]
    cases += [
        {"id": "ascii-space", "text": "1 234,56", "input": "1234.56"},
        {"id": "multiple-spaces", "text": "1   234,56", "input": "1234.56"},
        {"id": "malformed-groups", "text": "1 23 456,78", "input": None},
        {"id": "accounting", "text": "(1 234,56)", "input": "-1234.56"},
        {"id": "rate", "text": "12 345%", "input": None},
    ]
    output = HERE / "fixtures"
    output.mkdir(exist_ok=True)
    canvas = Canvas(str(output / "numbers.pdf"), pagesize=(612, 792), invariant=True)
    canvas.setTitle("Controlled space-separated numeric evidence")
    canvas.setAuthor("Anton Soloviev")
    for case in cases:
        canvas.setFont("Helvetica", 12)
        canvas.drawString(40, 750, "Authored evidence control: " + case["id"])
        canvas.setFont("SpaceNumbers", 20)
        canvas.drawString(40, 670, "Total " + case["text"])
        canvas.showPage()
    # The same flattened text represents two different physical layouts.
    for identifier, gap in [("wide-columns", 100), ("tight-values", 5)]:
        canvas.setFont("Helvetica", 12)
        canvas.drawString(40, 750, "Authored evidence control: " + identifier)
        x = 40.0
        for word in ["Fuel surcharge", "1", "210.50", "210.50"]:
            canvas.drawString(x, 670, word)
            x += pdfmetrics.stringWidth(word, "Helvetica", 12) + gap
        canvas.showPage()
        cases.append(
            {"id": identifier, "text": "Fuel surcharge 1 210.50 210.50", "layout": identifier}
        )
    canvas.save()
    (HERE / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n")
    review = Canvas(str(output / "review.pdf"), pagesize=(612, 792), invariant=True)
    review.setTitle("Controlled spaced total")
    review.setAuthor("Anton Soloviev")
    review.setFont("Helvetica", 20)
    review.drawString(40, 745, "Locale Supplies")
    review.setFont("Helvetica", 12)
    review.drawString(40, 710, "Invoice: SPACE-2026-17")
    review.drawString(40, 685, "Issued: 2026-10-17")
    review.setFont("SpaceNumbers", 24)
    review.drawString(40, 615, "Total due: 1\u202f234,56")
    review.setFont("Helvetica", 10)
    review.drawString(40, 555, "Synthetic invoice. No real transaction or OCR accuracy claim.")
    review.drawString(40, 535, "A grouping space must not turn 1234.56 into the amount 234.56.")
    review.save()
    data = {
        "vendor_name": {"value": "Locale Supplies", "evidence": ["Locale Supplies"]},
        "invoice_number": {"value": "SPACE-2026-17", "evidence": ["SPACE-2026-17"]},
        "issue_date": {"value": "2026-10-17", "evidence": ["2026-10-17"]},
        "total": {"value": 234.56, "evidence": ["Total due: 1\u202f234,56"]},
    }
    (output / "review.json").write_text(
        json.dumps({"schema": "invoice", "data": data}, ensure_ascii=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
