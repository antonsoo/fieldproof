#!/usr/bin/env python3
"""Precompute the static Pages demo's data: for each sample document, run
the real grounding + verification pipeline (fixture provider - no API key
needed) and write its page images and result JSON into web/public/demo-data/.

This is what "the demo shows the real grounding and verification output,
precomputed into JSON by the Python pipeline at build time" means concretely
- the web app never re-runs Python; it just renders what this script wrote.

Run: `uv run python scripts/build_demo_data.py` (also invoked by
`.github/workflows/pages.yml` before the Vite build).
"""

from __future__ import annotations

import json
from pathlib import Path

from fieldproof.document.loader import load_pdf
from fieldproof.document.render import render_page_png
from fieldproof.extract.fixture_provider import FixtureExtractor
from fieldproof.schemas import BUILTIN_SCHEMAS
from fieldproof.verify.engine import verify

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = ROOT / "examples"
OUT_DIR = ROOT / "web" / "public" / "demo-data"

SAMPLES = ["invoice", "receipt", "contract"]


def build_sample(name: str) -> None:
    pdf_path = EXAMPLES_DIR / f"{name}.pdf"
    fixture_path = EXAMPLES_DIR / "fixtures" / f"{name}.json"
    schema = BUILTIN_SCHEMAS[name]

    document = load_pdf(pdf_path)
    extraction = FixtureExtractor(fixture_path=fixture_path).extract(document, schema)
    report = verify(extraction.data, document)

    sample_dir = OUT_DIR / name
    sample_dir.mkdir(parents=True, exist_ok=True)

    for page in document.pages:
        png_bytes = render_page_png(pdf_path, page.number, scale=2.0)
        (sample_dir / f"page-{page.number}.png").write_bytes(png_bytes)

    payload = {
        "document": {
            "id": name,
            "filename": pdf_path.name,
            "page_count": document.page_count,
            "pages": [
                {"number": p.number, "width": p.width, "height": p.height} for p in document.pages
            ],
        },
        "extraction": {
            **extraction.to_dict(),
            "report": report.to_dict(),
            "review": {f.path: {"status": "pending", "edited_value": None} for f in report.fields},
        },
    }
    (sample_dir / "data.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {sample_dir}/data.json + {document.page_count} page image(s)")


def build_index() -> None:
    index = [{"id": name, "label": name.capitalize()} for name in SAMPLES]
    (OUT_DIR / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in SAMPLES:
        build_sample(name)
    build_index()


if __name__ == "__main__":
    main()
