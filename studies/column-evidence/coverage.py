"""Observe header coverage on pinned public invoice2data PDFs, without redistributing them.

This runs the header recognizer, not an independent accuracy oracle. No model
claims are synthesized and no field-correctness conclusion follows from it.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--src", required=True, type=Path)
parser.add_argument("--corpus", required=True, type=Path)
parser.add_argument("--out", required=True, type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.src.resolve()))
from fieldproof.document.loader import load_pdf
from fieldproof.schemas import Invoice
from fieldproof.verify.columns import _header, _lines
from fieldproof.verify.rows import default_row_rules

pin = "09378126e3ae86ddef5435ba166b4fc026e386a4"
assert (
    subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.corpus, text=True).strip() == pin
)
assert not subprocess.check_output(
    ["git", "status", "--porcelain"], cwd=args.corpus, text=True
).strip()
rule = default_row_rules(Invoice.model_construct())[0]
records = []
for pdf in sorted((args.corpus / "tests/compare").glob("*.pdf")):
    document = load_pdf(pdf)
    found = [
        {"page": page.number, "labels": {k: " ".join(w.text for w in v) for k, v in header.items()}}
        for page in document.pages
        for line in _lines(page.words)
        if (header := _header(line, rule)) is not None
    ]
    records.append(
        {
            "file": str(pdf.relative_to(args.corpus)),
            "bytes": pdf.stat().st_size,
            "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "pages": document.page_count,
            "recognized_headers": found,
        }
    )
result = {
    "repository": "https://github.com/invoice-x/invoice2data",
    "commit": pin,
    "license": "MIT, Copyright (c) 2015 Manuel Riel; PDFs are not redistributed",
    "scope": "Header coverage only, not claim verification or an accuracy measurement.",
    "records": records,
}
args.out.write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            "pdfs": len(records),
            "recognized_headers": sum(len(r["recognized_headers"]) for r in records),
        }
    )
)
