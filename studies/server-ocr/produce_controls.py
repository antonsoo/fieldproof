"""Native ReportLab controls: one mixed text/image invoice and a page-budget input.

The amounts and company are authored controls, not transactions or model output.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from fieldproof.document.render import render_page_png

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "fixtures"


def main():
    attachment = io.BytesIO()
    page = canvas.Canvas(attachment, pagesize=(612, 792), invariant=1)
    page.setFont("Helvetica", 16)
    page.drawString(60, 720, "SYNTHETIC ATTACHMENT - no real transaction")
    page.setFont("Helvetica", 24)
    page.drawString(60, 600, "Total: $100.00")
    page.showPage()
    page.save()
    image = render_page_png(attachment.getvalue(), 1)
    mixed = io.BytesIO()
    pdf = canvas.Canvas(mixed, pagesize=(612, 792), invariant=1)
    pdf.setFont("Helvetica", 16)
    pdf.drawString(60, 730, "SYNTHETIC CONTROL - no real transaction")
    for y, text in [
        (680, "Vendor: Source Lab"),
        (640, "Invoice: MIX-001"),
        (600, "Issued: 2026-10-20"),
    ]:
        pdf.drawString(60, y, text)
    pdf.showPage()
    pdf.drawImage(ImageReader(io.BytesIO(image)), 0, 0, width=612, height=792)
    pdf.showPage()
    pdf.save()
    (OUT / "mixed-source.pdf").write_bytes(mixed.getvalue())

    def evidence(value, quote):
        return {"value": value, "evidence": [quote]}

    fixture = {
        "schema": "invoice",
        "data": {
            "vendor_name": evidence("Source Lab", "Vendor: Source Lab"),
            "invoice_number": evidence("MIX-001", "Invoice: MIX-001"),
            "issue_date": evidence("2026-10-20", "Issued: 2026-10-20"),
            "total": evidence(100, "Total: $100.00"),
        },
    }
    (OUT / "mixed-fixture.json").write_text(json.dumps(fixture, indent=2) + "\n")
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=(300, 400), invariant=1)
    for i in range(9):
        pdf.drawString(30, 300, f"SYNTHETIC PAGE {i + 1}")
        pdf.showPage()
    pdf.save()
    (OUT / "nine-pages.pdf").write_bytes(buf.getvalue())
    blank = io.BytesIO()
    pdf = canvas.Canvas(blank, pagesize=(300, 400), invariant=1)
    pdf.showPage()
    pdf.save()
    (OUT / "blank.pdf").write_bytes(blank.getvalue())


if __name__ == "__main__":
    main()
