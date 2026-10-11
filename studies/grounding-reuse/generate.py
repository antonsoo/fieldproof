"""Make controlled, ordinary-sized invoice PDFs and fixture extractions; no model call."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def generate(rows: int, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, invariant=1)
    pdf.setTitle(f"Synthetic {rows}-row grounding performance invoice")
    items = []

    def field(value: str | float, evidence: str, page: int) -> dict:
        return {"value": value, "evidence": [evidence], "page": page}

    for start in range(0, rows, 50):
        page = start // 50 + 1
        pdf.setFont("Helvetica", 9)
        pdf.drawString(40, 805, "Synthetic Parts Co.     Invoice PERF-001     2026-10-11")
        pdf.drawString(
            40,
            782,
            "Description                                 Quantity                 Unit price"
            "              Amount",
        )
        for index in range(start, min(rows, start + 50)):
            y = 762 - (index - start) * 13
            label = f"Component {index + 1:04d}"
            for x, value in [(40, label), (275, "1"), (360, "12.00"), (465, "12.00")]:
                pdf.drawString(x, y, value)
            items.append(
                {
                    "description": field(label, label, page),
                    "quantity": field(1, "1", page),
                    "unit_price": field(12, "12.00", page),
                    "amount": field(12, "12.00", page),
                }
            )
        if start + 50 >= rows:
            pdf.drawString(390, 70, f"Total USD {rows * 12:.2f}")
        pdf.showPage()
    pdf.save()
    (destination / f"rows-{rows}.pdf").write_bytes(buffer.getvalue())
    data = {
        "vendor_name": field("Synthetic Parts Co.", "Synthetic Parts Co.", 1),
        "invoice_number": field("PERF-001", "PERF-001", 1),
        "issue_date": field("2026-10-11", "2026-10-11", 1),
        "total": field(rows * 12, f"{rows * 12:.2f}", (rows + 49) // 50),
        "line_items": items,
    }
    (destination / f"rows-{rows}.json").write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", nargs="+", type=int, default=[25, 50, 100, 400])
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "fixtures")
    args = parser.parse_args()
    for count in args.rows:
        if not 1 <= count <= 450:
            parser.error("use between 1 and 450 rows to stay inside the review field budget")
        generate(count, args.out)
