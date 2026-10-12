"""Compare OCR word boxes with direct Tesseract TSV; retain the visible review case.

This checks transport, offsets and coordinate conversion, not recognition accuracy.
Run with the interpreter of the installed package being inspected.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import io
import json
import platform
import subprocess
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import pytesseract

from fieldproof.document.ocr import load_scanned_pdf
from fieldproof.document.render import render_page_png
from fieldproof.extract.fixture_provider import FixtureExtractor
from fieldproof.schemas.receipt import Receipt
from fieldproof.verify.engine import verify

STUDY = Path(__file__).resolve().parent
ROOT = STUDY.parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    records = []
    for name in ("scanned-invoice", "scanned-receipt", "scanned-contract", "blank-then-invoice"):
        source = STUDY / "inputs" / f"{name}.pdf"
        started = time.perf_counter()
        document = load_scanned_pdf(source)
        elapsed = time.perf_counter() - started
        raw = asdict(document)
        raw["source"] = source.name
        (args.out / f"{name}-document.json").write_text(json.dumps(raw, indent=2) + "\n")
        for page in document.pages:
            raster = render_page_png(source, page.number)
            with tempfile.TemporaryDirectory(prefix="ocr-tsv-") as temporary:
                image = Path(temporary) / "page.png"
                image.write_bytes(raster)
                direct = subprocess.run(
                    [
                        pytesseract.pytesseract.tesseract_cmd,
                        str(image),
                        "stdout",
                        "-l",
                        "eng",
                        "tsv",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            expected = []
            for row in csv.DictReader(
                io.StringIO(direct.stdout), delimiter="\t", quoting=csv.QUOTE_NONE
            ):
                if not row["text"].strip():
                    continue
                left, top, width, height = (
                    int(row[key]) for key in ("left", "top", "width", "height")
                )
                expected.append(
                    {
                        "text": row["text"].strip(),
                        "bbox": {
                            "x0": left / 2,
                            "top": top / 2,
                            "x1": (left + width) / 2,
                            "bottom": (top + height) / 2,
                        },
                    }
                )
            actual = [{"text": word.text, "bbox": word.bbox.to_dict()} for word in page.words]
            assert actual == expected, (name, page.number)
            assert all(page.text[word.start : word.end] == word.text for word in page.words)
            assert all(
                0 <= word.bbox.x0 < word.bbox.x1 <= page.width
                and 0 <= word.bbox.top < word.bbox.bottom <= page.height
                for word in page.words
            )
            (args.out / f"{name}-page-{page.number}.tsv").write_text(direct.stdout)
        records.append(
            {
                "input": source.name,
                "pages": len(document.pages),
                "words": sum(len(page.words) for page in document.pages),
                "elapsedSeconds": elapsed,
                "allWordsAndBoxesMatchDirectTSV": True,
            }
        )
        if name == "scanned-receipt":
            extraction = FixtureExtractor(ROOT / "examples/fixtures/receipt.json").extract(
                document, Receipt
            )
            report = verify(extraction.data, document)
            fields = [field for field in report.fields if field.path.startswith("items[2].")]
            assert all(field.status == "needs_review" for field in fields)
            raster = render_page_png(source, 1)
            page = document.page(1)
            rectangles = "".join(
                f'<rect x="{r["x0"]}" y="{r["top"]}" width="{r["x1"] - r["x0"]}" '
                f'height="{r["bottom"] - r["top"]}" fill="none" stroke="#b32020" stroke-width="1"/>'
                for field in fields
                for r in field.rects
            )
            details = "".join(
                f"<p><b>{html.escape(field.path)}</b>: {html.escape(str(field.value))}"
                f"<br>OCR: {html.escape(field.matched_text or '')}"
                f"<br>{html.escape('; '.join(field.reasons))}</p>"
                for field in fields
            )
            figure = (
                '<!doctype html><meta charset="utf-8"><title>Actual OCR evidence</title>'
                "<style>body{font:16px/1.5 system-ui;margin:24px;color:#222;max-width:1000px}"
                "svg{width:450px;max-width:100%;height:auto;border:1px solid #bbb}"
                "p{max-width:800px}h1{font-size:24px}</style>"
                "<h1>OCR evidence: Cold Brew 16oz</h1>"
                "<p>Synthetic receipt, rasterized to an image-only PDF. Tesseract reads "
                "160z; all three affected row fields need review. Red boxes are the actual "
                "verification report coordinates.</p>"
                f'<svg viewBox="0 0 {page.width} {page.height}" xmlns="http://www.w3.org/2000/svg">'
                f'<image width="{page.width}" height="{page.height}" href="data:image/png;base64,'
                f'{base64.b64encode(raster).decode()}"/>{rectangles}</svg>{details}'
            )
            (args.out / "receipt-evidence.html").write_text(figure)

    started = time.perf_counter()
    try:
        load_scanned_pdf(STUDY / "inputs/scanned-invoice.pdf", timeout=0.000001)
    except RuntimeError as exc:
        assert "timeout" in str(exc)
        timeout = {"error": str(exc), "elapsedSeconds": time.perf_counter() - started}
    else:
        raise AssertionError("actual Tesseract unexpectedly finished within one microsecond")
    receipt = {
        "python": platform.python_version(),
        "engine": str(pytesseract.get_tesseract_version()),
        "pytesseract": pytesseract.__version__,
        "inputs": records,
        "actualTimeout": timeout,
        "files": [
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in sorted(args.out.iterdir())
            if path.is_file() and path.name != "oracle.json"
        ],
    }
    (args.out / "oracle.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        f"Direct TSV agrees for {sum(item['words'] for item in records)} words; "
        "actual timeout terminated"
    )


if __name__ == "__main__":
    main()
