"""Reproducible local PDF worker measurements; needs dev + OCR extras on Linux."""

import argparse
import io
import json
import resource
import time
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from fieldproof.document.loader import EmptyDocumentError
from fieldproof.server.pdf_work import load_server_pdf, render_server_page

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, help="write the measurements to JSON as well as stdout")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
long = io.BytesIO()
pdf = canvas.Canvas(long, pagesize=(612, 792))
for page in range(64):
    for line in range(40):
        pdf.drawString(
            24,
            760 - line * 17,
            f"Page {page + 1} line {line + 1}: representative native PDF text with numbers 123.45",
        )
    pdf.showPage()
pdf.save()
image = Image.new("RGB", (1600, 2200), "white")
draw = ImageDraw.Draw(image)
for y in range(80, 2100, 40):
    draw.text(
        (100, y), "Synthetic scanned invoice: vendor, amount 123.45, date 2026-10-04", fill="black"
    )
scan = io.BytesIO()
pdf = canvas.Canvas(scan, pagesize=(612, 792))
pdf.drawImage(ImageReader(image), 0, 0, width=612, height=792)
pdf.save()
cases = [
    (name, (root / f"examples/{name}.pdf").read_bytes())
    for name in ("invoice", "receipt", "contract")
]
cases += [("native-64-pages", long.getvalue()), ("image-only-scan", scan.getvalue())]
measurements = []
for name, content in cases:
    start = time.perf_counter()
    try:
        document = load_server_pdf(content, f"{name}.pdf")
        outcome = "loaded"
        words = sum(len(p.words) for p in document.pages)
        pages = document.page_count
    except EmptyDocumentError:
        outcome = "refused: no text layer"
        words = 0
        pages = 1
    elapsed = time.perf_counter() - start
    start = time.perf_counter()
    rendered = render_server_page(content, 1)
    measurements.append(
        dict(
            case=name,
            pdf_bytes=len(content),
            pages=pages,
            words=words,
            outcome=outcome,
            load_seconds=round(elapsed, 3),
            render_seconds=round(time.perf_counter() - start, 3),
            png_bytes=len(rendered),
            largest_child_peak_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        )
    )
result = {
    "description": (
        "Single local run; largest-child RSS is cumulative across completed workers, "
        "not a per-case delta. No live provider or OCR accuracy measurement."
    ),
    "cases": measurements,
    "parent_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
}
if args.out is not None:
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
