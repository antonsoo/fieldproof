"""Render the captured native numeric parts with an explicitly supplied Unicode font.

    python make_fixtures.py --font /path/to/DejaVuSans.ttf

The committed fixture needs no font installation to replay. Regeneration needs
ReportLab and DejaVu Sans; the embedded subset's license is beside this script.
"""

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
    pdfmetrics.registerFont(TTFont("LocaleNumbers", str(args.font)))
    cases = json.loads((HERE / "intl.json").read_text())["cases"]
    canvas = Canvas(str(HERE / "fixtures/numbers.pdf"), pagesize=(612, 792), invariant=True)
    canvas.setTitle("Authored numeric evidence controls")
    canvas.setAuthor("Anton Soloviev")
    for case in cases:
        canvas.setFont("Helvetica", 12)
        canvas.drawString(40, 750, "Fieldproof numeric evidence control: " + case["id"])
        canvas.drawString(
            40, 725, "Authored PDF; native Intl numeric parts; no OCR accuracy claim."
        )
        canvas.setFont("LocaleNumbers", 20)
        canvas.drawString(40, 670, case["id"] + " total: " + case["numericText"])
        canvas.showPage()
    canvas.save()
    review = Canvas(str(HERE / "fixtures/review.pdf"), pagesize=(612, 792), invariant=True)
    review.setTitle("Controlled locale invoice")
    review.setAuthor("Anton Soloviev")
    review.setFont("Helvetica", 20)
    review.drawString(40, 745, "Locale Supplies")
    review.setFont("Helvetica", 12)
    review.drawString(40, 710, "Invoice: NUM-2026-17")
    review.drawString(40, 685, "Issued: 2026-10-17")
    review.setFont("LocaleNumbers", 24)
    review.drawString(40, 615, "Total due: " + cases[0]["numericText"])
    review.setFont("Helvetica", 10)
    review.drawString(
        40, 555, "Synthetic invoice for numeric evidence review. No real transaction."
    )
    review.drawString(40, 535, "The fixture claims 234; the printed amount is 1234.56.")
    review.save()


if __name__ == "__main__":
    main()
