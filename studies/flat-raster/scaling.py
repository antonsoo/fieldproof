"""Observed loader cost on authored 1/10/50-page ledgers; not a latency guarantee."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter


def measure(pages: int) -> dict:
    from reportlab.pdfgen.canvas import Canvas

    from fieldproof.document.loader import load_pdf

    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=(612, 792), invariant=True)
    for page in range(pages):
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
    content = stream.getvalue()
    load_pdf(content)
    seconds = []
    frame_hash = None
    states = None
    words = None
    for _ in range(3):
        started = perf_counter()
        document = load_pdf(content)
        seconds.append(perf_counter() - started)
        frames = [
            {
                "text": page.text,
                "width": page.width,
                "height": page.height,
                "words": [[w.text, w.start, w.end, w.bbox.to_dict()] for w in page.words],
            }
            for page in document.pages
        ]
        observed = hashlib.sha256(json.dumps(frames, sort_keys=True).encode()).hexdigest()
        if frame_hash is not None:
            assert frame_hash == observed
        frame_hash = observed
        states = dict(
            Counter(
                getattr(w, "raster_state", None) or "not_recorded"
                for p in document.pages
                for w in p.words
            )
        )
        words = sum(len(page.words) for page in document.pages)
        del document, frames
    return {
        "pages": pages,
        "bytes": len(content),
        "sourceSha256": hashlib.sha256(content).hexdigest(),
        "words": words,
        "geometrySha256": frame_hash,
        "rasterStates": states,
        "medianSeconds": statistics.median(seconds),
        "seconds": seconds,
        "processPeakRssBytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", type=int)
    args = parser.parse_args()
    if args.child is not None:
        print(json.dumps(measure(args.child)))
        return
    assert args.output is not None
    rows = []
    for pages in (1, 10, 50):
        row = json.loads(
            subprocess.check_output(
                [sys.executable, str(Path(__file__).resolve()), "--child", str(pages)], text=True
            )
        )
        rows.append(row)
        print(
            f"{pages} pages: {row['words']} words, median {row['medianSeconds']:.3f}s", flush=True
        )
    result = {
        "scope": __doc__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "logicalCpus": os.cpu_count(),
        "loadAverage": os.getloadavg(),
        "warmups": 1,
        "repeats": 3,
        "rows": rows,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
