"""Authored PDFs: invisible paint, flat occlusion, partial digits and visible controls."""

from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

HERE = Path(__file__).resolve().parent
ALTERNATE = "Authorized total: $900.00"
VISIBLE = "Visible total: $90.00"
FOOTER = "Footer control"


def label_image(text: str) -> Image.Image:
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=(550, 90), invariant=True)
    pdf.setFont("Helvetica", 16)
    pdf.drawString(10, 40, text)
    pdf.save()
    with pdfium.PdfDocument(stream.getvalue()) as document:
        page = document[0]
        try:
            bitmap = page.render(scale=2)
            try:
                image = bitmap.to_pil()
                try:
                    return image.convert("RGB")
                finally:
                    image.close()
            finally:
                bitmap.close()
        finally:
            page.close()


def stripes(pdf: Canvas, *, opaque: bool) -> None:
    if opaque:
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(30, 560, 550, 90, fill=1, stroke=0)
    pdf.setFillColorRGB(*([0, 0, 0] if opaque else [0.8, 0.8, 0.8]))
    for x in range(30, 580, 4):
        pdf.rect(x, 560, 1, 90, fill=1, stroke=0)


def draw_case(case: dict, *, omit_hidden: bool = False) -> bytes:
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=tuple(case.get("page_size", (612, 792))), invariant=True)
    pdf.setFont("Helvetica", 16)
    pdf.drawString(40, 700, VISIBLE)
    pdf.saveState()
    bg = case.get("background", [1, 1, 1])
    fg = case.get("foreground", [0, 0, 0])
    pdf.setFillColorRGB(*bg)
    pdf.rect(30, 560, 550, 90, fill=1, stroke=0)
    size = case.get("font_size", 16)
    pdf.setFont("Helvetica", size)
    kind = case.get("kind", "line")
    if kind == "pattern-background":
        stripes(pdf, opaque=False)
    if kind == "hole":
        pdf._code.append("0 0 612 792 re 30 560 550 90 re W* n")
    pdf.setFillColorRGB(*fg)
    if kind in {"leading-digit", "mixed-visible"}:
        x = 40.0
        for char in ALTERNATE:
            hidden = char == "9"
            pdf.setFillColorRGB(
                *(bg if hidden and kind == "leading-digit" else ([0.7, 0, 0] if hidden else fg))
            )
            if not (omit_hidden and hidden and case["hidden"]):
                pdf.drawString(x, 600, char)
            x += pdf.stringWidth(char, "Helvetica", size)
    elif not (omit_hidden and case["hidden"]):
        pdf.drawString(40, 600, ALTERNATE)
    if kind == "pattern":
        stripes(pdf, opaque=True)
    if kind in {"overpaint", "image", "image-text"}:
        if kind == "overpaint":
            pdf.setFillColorRGB(*bg)
            pdf.rect(30, 560, 550, 90, fill=1, stroke=0)
        else:
            image = (
                label_image("Authorized total: $90.00")
                if kind == "image-text"
                else Image.new("RGB", (8, 8), tuple(round(v * 255) for v in bg))
            )
            try:
                pdf.drawImage(ImageReader(image), 30, 560, 550, 90)
            finally:
                image.close()
    pdf.restoreState()
    pdf.setFont("Helvetica", 16)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.drawString(40, 450, FOOTER)
    pdf.save()
    content = stream.getvalue()
    if case.get("rotation") or case.get("crop"):
        with pdfium.PdfDocument(content) as document:
            page = document[0]
            try:
                if case.get("rotation"):
                    page.set_rotation(case["rotation"])
                if case.get("crop"):
                    page.set_cropbox(*case["crop"])
                output = io.BytesIO()
                document.save(output)
                content = output.getvalue()
                # PDFium refreshes the second trailer ID on save. Derive that
                # non-rendering identifier from authored input instead, so the
                # retained rotated/cropped PDF bytes regenerate exactly.
                identifier = (
                    hashlib.sha256(stream.getvalue() + json.dumps(case, sort_keys=True).encode())
                    .hexdigest()[:32]
                    .upper()
                    .encode()
                )
                content, replaced = re.subn(
                    rb"(/ID\s*\[\s*<[^>]+>\s*<)[^>]+(>\s*\])",
                    lambda match: match.group(1) + identifier + match.group(2),
                    content,
                    count=1,
                )
                assert replaced == 1
            finally:
                page.close()
    return content


def cases() -> list[dict]:
    result = [
        {"id": "black-on-white", "hidden": False},
        {"id": "a4-visible", "page_size": [595.2756, 841.8898], "hidden": False},
        {
            "id": "a4-white-on-white",
            "page_size": [595.2756, 841.8898],
            "foreground": [1, 1, 1],
            "hidden": True,
        },
        {"id": "white-on-white", "foreground": [1, 1, 1], "hidden": True},
        {"id": "black-on-black", "background": [0, 0, 0], "hidden": True},
        {
            "id": "gray-on-gray",
            "background": [0.5, 0.5, 0.5],
            "foreground": [0.5, 0.5, 0.5],
            "hidden": True,
        },
        {"id": "white-on-black", "background": [0, 0, 0], "foreground": [1, 1, 1], "hidden": False},
        {"id": "black-on-yellow", "background": [1, 1, 0.7], "hidden": False},
        {
            "id": "white-on-blue",
            "background": [0.1, 0.2, 0.5],
            "foreground": [1, 1, 1],
            "hidden": False,
        },
        {"id": "overpaint-white", "kind": "overpaint", "hidden": True},
        {
            "id": "overpaint-gray",
            "kind": "overpaint",
            "background": [0.5, 0.5, 0.5],
            "hidden": True,
        },
        {"id": "flat-image-cover", "kind": "image", "hidden": True},
        {"id": "image-prints-ninety", "kind": "image-text", "hidden": True},
        {"id": "pattern-covers-text", "kind": "pattern", "hidden": True},
        {"id": "text-over-pattern", "kind": "pattern-background", "hidden": False},
        {"id": "even-odd-hole", "kind": "hole", "hidden": True},
        {"id": "leading-nine-hidden", "kind": "leading-digit", "hidden": True},
        {"id": "mixed-ink-visible", "kind": "mixed-visible", "hidden": False},
    ]
    for size in (8, 24):
        result.extend(
            [
                {
                    "id": f"white-on-white-{size}pt",
                    "font_size": size,
                    "foreground": [1, 1, 1],
                    "hidden": True,
                },
                {"id": f"visible-{size}pt", "font_size": size, "hidden": False},
                {
                    "id": f"leading-nine-hidden-{size}pt",
                    "kind": "leading-digit",
                    "font_size": size,
                    "hidden": True,
                },
            ]
        )
    for angle in (90, 180, 270):
        result.extend(
            [
                {
                    "id": f"white-on-white-rot{angle}",
                    "rotation": angle,
                    "foreground": [1, 1, 1],
                    "hidden": True,
                },
                {
                    "id": f"white-on-black-rot{angle}",
                    "rotation": angle,
                    "background": [0, 0, 0],
                    "foreground": [1, 1, 1],
                    "hidden": False,
                },
            ]
        )
    for angle in (0, 90):
        result.extend(
            [
                {
                    "id": f"white-crop-rot{angle}",
                    "crop": [20, 20, 500, 760],
                    "rotation": angle,
                    "foreground": [1, 1, 1],
                    "hidden": True,
                },
                {
                    "id": f"visible-crop-rot{angle}",
                    "crop": [20, 20, 500, 760],
                    "rotation": angle,
                    "hidden": False,
                },
            ]
        )
    return result


def generate() -> None:
    directory = HERE / "fixtures"
    directory.mkdir(exist_ok=True)
    authored = cases()
    for case in authored:
        (directory / f"{case['id']}.pdf").write_bytes(draw_case(case))
    (HERE / "cases.json").write_text(json.dumps(authored, indent=2) + "\n")
    data = {
        "vendor_name": {"value": "Example", "evidence": []},
        "invoice_number": {"value": "RASTER-0", "evidence": []},
        "issue_date": {"value": "2026-10-16", "evidence": []},
        "total": {"value": 900, "evidence": [ALTERNATE], "page": 1},
    }
    (HERE / "fixture.json").write_text(json.dumps(data, indent=2) + "\n")
    (HERE / "extraction.json").write_text(
        json.dumps({"schema": "invoice", "data": data}, indent=2) + "\n"
    )
    print(f"Generated {len(authored)} authored PDF cases")


def demo_sample() -> None:
    """An existing-demo sample whose only bad field comes from invisible text."""
    examples = HERE.parents[1] / "examples"
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=(612, 792), invariant=True)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, 750, "SYNTHETIC REVIEW SAMPLE - NO REAL INVOICE")
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(40, 710, "Invoice VIS-009")
    pdf.setFont("Helvetica", 14)
    pdf.drawString(40, 675, "Example Tools Ltd.")
    pdf.drawString(40, 650, "Issued: 2026-10-16")
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawString(40, 590, "Visible total: $90.00")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, 545, "This PDF has an additional, invisible amount in its text layer.")
    pdf.drawString(
        40, 529, "The fixture extracts that amount so the verifier must keep it in review."
    )
    pdf.setFont("Helvetica", 16)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.drawString(40, 450, ALTERNATE)
    with label_image("Authorized total: $90.00") as image:
        pdf.drawImage(ImageReader(image), 30, 410, 550, 90)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont("Helvetica", 11)
    pdf.drawString(40, 390, "Select total and compare the quote with the printed $90.00.")
    pdf.save()
    (examples / "hidden-text.pdf").write_bytes(stream.getvalue())
    data = {
        "vendor_name": {"value": "Example Tools Ltd.", "evidence": ["Example Tools Ltd."]},
        "invoice_number": {"value": "VIS-009", "evidence": ["Invoice VIS-009"]},
        "issue_date": {"value": "2026-10-16", "evidence": ["Issued: 2026-10-16"]},
        "total": {"value": 900, "evidence": [ALTERNATE]},
    }
    (examples / "fixtures/hidden-text.json").write_text(
        json.dumps({"schema": "invoice", "data": data}, indent=2) + "\n"
    )


if __name__ == "__main__":
    generate()
    demo_sample()
