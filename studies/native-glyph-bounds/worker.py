"""Measure actual installed PDF workers on one reproducible 64-page ledger.

Author the input with --author in a development environment; replaying that PDF
only needs Fieldproof's runtime dependencies. This is one local observation.
"""

import argparse
import hashlib
import json
import platform
import resource
from collections import Counter
from pathlib import Path
from time import perf_counter

from fieldproof.server.pdf_work import load_server_pdf, render_server_page

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("pdf", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument("--author", action="store_true")
args = parser.parse_args()
if args.author:
    from reportlab.pdfgen.canvas import Canvas

    pdf = Canvas(str(args.pdf), pagesize=(612, 792), invariant=True)
    for page in range(64):
        pdf.setFont("Helvetica", 14)
        pdf.drawString(40, 750, f"Synthetic ledger page {page + 1}")
        pdf.setFont("Helvetica", 10)
        for row in range(45):
            number = page * 45 + row + 1
            pdf.drawString(
                40,
                700 - row * 14,
                f"Line {number:04d} Widget Alpha quantity 2 unit 12.50 amount 25.00",
            )
        pdf.showPage()
    pdf.save()
content = args.pdf.read_bytes()
started = perf_counter()
document = load_server_pdf(content, "synthetic-64-pages.pdf")
load_seconds = perf_counter() - started
states = Counter(w.raster_state for p in document.pages for w in p.words)
assert document.page_count == 64 and states == {"contributes": 29056}, states
started = perf_counter()
png = render_server_page(content, 1)
render_seconds = perf_counter() - started
assert png.startswith(b"\x89PNG\r\n\x1a\n")
result = {
    "scope": "Actual server workers; one local observation, not a performance guarantee.",
    "python": platform.python_version(),
    "sourceSha256": hashlib.sha256(content).hexdigest(),
    "sourceBytes": len(content),
    "pages": document.page_count,
    "words": sum(states.values()),
    "rasterStates": dict(states),
    "loadSeconds": load_seconds,
    "renderSeconds": render_seconds,
    "pngBytes": len(png),
    "pngSha256": hashlib.sha256(png).hexdigest(),
    "largestChildPeakRssBytes": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024,
    "limits": {
        "wallSecondsPerOperation": 30,
        "cpuSecondsPerWorker": 20,
        "addressSpaceBytes": 768 * 1024 * 1024,
    },
}
args.output.write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            k: result[k]
            for k in ("words", "loadSeconds", "renderSeconds", "largestChildPeakRssBytes")
        }
    )
)
