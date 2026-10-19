"""Observe actual local OCR of a form-only page; preserve the recognized words."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from fieldproof.document.loader import EmptyDocumentError
from fieldproof.document.ocr import load_scanned_pdf
from fieldproof.document.render import render_page_png

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = (HERE / "fixtures/form-only.pdf").read_bytes()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "review.png").write_bytes(render_page_png(source, 1))
    result = {"source_sha256": hashlib.sha256(source).hexdigest()}
    try:
        document = load_scanned_pdf(source)
        result["status"] = "recognized"
        result["document"] = asdict(document)
    except EmptyDocumentError as error:
        result["status"] = "empty_recognition"
        result["error"] = str(error)
    (args.output / "ocr.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
