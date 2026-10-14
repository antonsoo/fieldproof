"""Author native headers and rasterized totals; synthetic PDFs, not scanner samples."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from fieldproof.document.render import render_page_png

ROOT = Path(__file__).resolve().parent


def header(pdf: Canvas) -> None:
    pdf.setFont("Helvetica", 16)
    for text, y in [
        ("Acme Laboratory", 720),
        ("Invoice MIXED-2026-07", 680),
        ("Issued 2026-07-01", 640),
    ]:
        pdf.drawString(72, y, text)


def totals(pdf: Canvas) -> None:
    pdf.setFont("Helvetica", 16)
    for text, y in [("Subtotal 120.00", 720), ("Tax 3.45", 680), ("Total 123.45", 640)]:
        pdf.drawString(72, y, text)


def main() -> None:
    directory = ROOT / "inputs"
    directory.mkdir(exist_ok=True)
    raster_source = io.BytesIO()
    source = Canvas(raster_source, pagesize=(612, 792), invariant=1)
    totals(source)
    source.save()
    png = render_page_png(raster_source.getvalue(), 1, scale=2)
    (directory / "totals.png").write_bytes(png)
    cases = {
        "native": ["header", "native-totals"],
        "mixed": ["header", "scan"],
        "scan-first": ["scan", "header"],
        "blank-middle": ["header", "blank", "scan"],
        "all-scanned": ["scan"],
    }
    records = []
    for name, order in cases.items():
        path = directory / f"{name}.pdf"
        pdf = Canvas(str(path), pagesize=(612, 792), invariant=1)
        for kind in order:
            if kind == "header":
                header(pdf)
            elif kind == "native-totals":
                totals(pdf)
            elif kind == "scan":
                pdf.drawImage(ImageReader(io.BytesIO(png)), 0, 0, width=612, height=792)
            pdf.showPage()
        pdf.save()
        data = {
            "vendor_name": {"value": "Acme Laboratory", "evidence": ["Acme Laboratory"]},
            "invoice_number": {"value": "MIXED-2026-07", "evidence": ["MIXED-2026-07"]},
            "issue_date": {"value": "2026-07-01", "evidence": ["2026-07-01"]},
            "subtotal": {"value": 120.0, "evidence": ["Subtotal 120.00"]},
            "tax": {"value": 3.45, "evidence": ["Tax 3.45"]},
            "total": {"value": 123.45, "evidence": ["Total 123.45"]},
        }
        for key, claim in data.items():
            kind = (
                "header"
                if key in {"vendor_name", "invoice_number", "issue_date"}
                else "native-totals"
                if name == "native"
                else "scan"
            )
            if kind in order:
                claim["page"] = order.index(kind) + 1
            else:
                claim["evidence"] = []
        (directory / f"{name}.json").write_text(
            json.dumps({"schema": "invoice", "data": data}, indent=2) + "\n"
        )
        records.append(
            {
                "file": path.name,
                "pages": order,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    (ROOT / "inputs.json").write_text(
        json.dumps(
            {
                "population": "Synthetic native text and PDFium-rasterized totals at 144 DPI; "
                "no camera, scanner or live model",
                "cases": records,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Wrote {len(records)} controlled PDFs")


if __name__ == "__main__":
    main()
