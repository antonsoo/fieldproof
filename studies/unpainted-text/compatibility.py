"""Record native text and geometry on the checkout's existing example PDFs."""

import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

from fieldproof.document.loader import load_pdf

root = Path(__file__).resolve().parents[2]
observations = []
for path in sorted((root / "examples").glob("*.pdf")):
    document = load_pdf(path)
    pages = [
        {
            "number": page.number, "width": page.width, "height": page.height, "text": page.text,
            "words": [
                {key: value for key, value in asdict(word).items() if key != "render_mode"}
                for word in page.words
            ],
        }
        for page in document.pages
    ]
    observations.append({
        "file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "pages": len(pages), "words": sum(len(page.words) for page in document.pages),
        "text_and_geometry_sha256": hashlib.sha256(
            json.dumps(pages, sort_keys=True).encode()
        ).hexdigest(),
    })
Path(sys.argv[1]).write_text(json.dumps(observations, indent=2) + "\n")
print(f"Recorded text and geometry for {len(observations)} existing example PDFs")
