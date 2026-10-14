"""Compare mixed-document native pages and raw Tesseract TSV with the actual loader."""

from __future__ import annotations

import argparse
import csv
import io
import json
import platform
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path

import pytesseract

from fieldproof.document.limits import DocumentLimitError, DocumentLimits
from fieldproof.document.loader import load_pdf
from fieldproof.document.ocr import load_pdf_with_ocr
from fieldproof.document.render import render_page_png

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    records = []
    for name in ["mixed", "scan-first", "blank-middle"]:
        source = ROOT / f"inputs/{name}.pdf"
        original = load_pdf(source)
        document = load_pdf_with_ocr(source)
        assert document.ocr is not None
        recognized = document.ocr.processed_pages
        assert recognized is not None
        pages = []
        for page in document.pages:
            if page.number not in recognized:
                assert asdict(page) == asdict(original.page(page.number))
                pages.append(
                    {"page": page.number, "nativePageUnchanged": True, "words": len(page.words)}
                )
                continue
            raster = render_page_png(source, page.number)
            with tempfile.TemporaryDirectory(prefix="mixed-tsv-") as temporary:
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
                left, top, width, height = [
                    int(row[key]) for key in ["left", "top", "width", "height"]
                ]
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
            assert actual == expected
            assert all(page.text[word.start : word.end] == word.text for word in page.words)
            assert all(
                0 <= word.bbox.x0 < word.bbox.x1 <= page.width
                and 0 <= word.bbox.top < word.bbox.bottom <= page.height
                for word in page.words
            )
            (args.out / f"{name}-page-{page.number}.tsv").write_text(direct.stdout)
            pages.append(
                {"page": page.number, "ocrWords": len(page.words), "matchesDirectTsv": True}
            )
        snapshot = asdict(document)
        snapshot["source"] = source.name
        (args.out / f"{name}-document.json").write_text(json.dumps(snapshot, indent=2) + "\n")
        records.append({"input": source.name, "processedPages": recognized, "pages": pages})

    failures = []
    for limits in [DocumentLimits(max_words=7), DocumentLimits(max_text_chars=55)]:
        try:
            load_pdf_with_ocr(ROOT / "inputs/mixed.pdf", limits=limits)
        except DocumentLimitError as exc:
            assert "Combined native and OCR" in str(exc)
            failures.append({"budget": asdict(limits), "rejectedCombinedText": True})
        else:
            raise AssertionError("Combined native/OCR text exceeded its budget")
    try:
        load_pdf_with_ocr(ROOT / "inputs/mixed.pdf", timeout=0.000001)
    except RuntimeError as exc:
        assert "page 2" in str(exc) and "timeout" in str(exc)
        timeout = {"page": 2, "actualRecognitionTimeoutRaised": True}
    else:
        raise AssertionError("Actual recognition unexpectedly completed within one microsecond")
    result = {
        "python": platform.python_version(),
        "tesseract": str(pytesseract.get_tesseract_version()),
        "pytesseract": pytesseract.__version__,
        "records": records,
        "combinedBudgetFailures": failures,
        "actualTimeout": timeout,
        "scope": "Actual same-recognizer TSV comparison checks retention and pixel-to-point "
        "conversion; it is not independent OCR accuracy evidence.",
    }
    (args.out / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Checked {len(records)} actual mixed documents; native pages unchanged, TSV/boxes agree")


if __name__ == "__main__":
    main()
