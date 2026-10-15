"""Author synthetic PDF controls; expected verdicts come from the draw operations."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pypdfium2 as pdfium
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parent


def text(pdf: Canvas, x: float, y: float, value: str, mode: int = 0) -> None:
    pdf.saveState()
    item = pdf.beginText(x, y)
    item.setFont("Helvetica", 14)
    item.setTextRenderMode(mode)
    item.textLine(value)
    pdf.drawText(item)
    pdf.restoreState()


def generate() -> list[dict]:
    directory = ROOT / "fixtures"
    directory.mkdir(parents=True, exist_ok=True)
    cases = []

    def save(name: str, draw, checks: list[dict], rotation: int = 0) -> None:
        stream = io.BytesIO()
        pdf = Canvas(stream, pagesize=(612, 792), invariant=True)
        text(pdf, 40, 750, "Synthetic rendering-mode control")
        draw(pdf)
        pdf.save()
        content = stream.getvalue()
        if rotation:
            with pdfium.PdfDocument(content) as document:
                page = document[0]
                page.set_rotation(rotation)
                output = io.BytesIO()
                document.save(output)
                page.close()
                content = output.getvalue()
        (directory / f"{name}.pdf").write_bytes(content)
        cases.append({"id": name, "checks": checks})

    def claim(value, quote: str, expected: str, path: str = "total") -> dict:
        return {"path": path, "value": value, "quote": quote, "expected": expected}

    layouts = [(f"mode-{mode}", mode, False, 0) for mode in range(8)]
    layouts += [(f"form-{mode}", mode, True, 0) for mode in (0, 3, 7)]
    layouts += [
        (f"rotated-{rotation}-mode-{mode}", mode, False, rotation)
        for rotation in (90, 180, 270) for mode in (3, 7)
    ]
    for name, mode, form, rotation in layouts:
        def draw(pdf, mode=mode, form=form):
            text(pdf, 40, 680, "Amount due: $100.00")
            if form:
                pdf.beginForm("alternate")
            text(pdf, 40, 600, "Authorized total: $900.00", mode)
            if form:
                pdf.endForm()
                pdf.doForm("alternate")
        save(name, draw, [
            claim(900, "Authorized total: $900.00",
                  "needs_review" if mode in (3, 7) else "verified"),
            claim(100, "Amount due: $100.00", "verified"),
        ], rotation)

    for mode in (3, 7):
        save(f"number-convention-{mode}", lambda pdf, mode=mode: (
            text(pdf, 40, 680, "Amount due: 60.000"),
            text(pdf, 40, 600, "Reference: 1.234,50", mode),
        ), [claim(value, "Amount due: 60.000", "needs_review") for value in (60, 60000)])
        save(f"date-convention-{mode}", lambda pdf, mode=mode: (
            text(pdf, 40, 680, "Issue date: 03/04/2026"),
            text(pdf, 40, 600, "Reference date: 31/12/2026", mode),
        ), [
            claim(value, "Issue date: 03/04/2026", "needs_review", "issue_date")
            for value in ("2026-03-04", "2026-04-03")
        ])
        save(f"row-anchor-{mode}", lambda pdf, mode=mode: (
            text(pdf, 40, 680, "Delivery", mode),
            text(pdf, 200, 680, "2"),
            text(pdf, 40, 600, "Packing 2"),
        ), [
            claim("Delivery", "Delivery", "needs_review", "items[0].description"),
            claim(2, "2", "needs_review", "items[0].quantity"),
        ])
    (ROOT / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")
    # A complete built-in-schema fixture for the actual CLI/API/browser flow.
    data = {
        "vendor_name": {"value": "Example", "evidence": []},
        "invoice_number": {"value": "MODE-3", "evidence": []},
        "issue_date": {"value": "2026-10-15", "evidence": []},
        "total": {"value": 900, "evidence": ["Authorized total: $900.00"], "page": 1},
    }
    (ROOT / "extraction.json").write_text(
        json.dumps({"schema": "invoice", "data": data}, indent=2) + "\n"
    )
    (ROOT / "fixture.json").write_text(json.dumps(data, indent=2) + "\n")
    return cases


if __name__ == "__main__":
    print(f"Generated {len(generate())} synthetic PDF controls")
