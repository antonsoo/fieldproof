"""Retain punctuation roles independently of uncertain amount boundaries.

Each page is one independent control. --generate uses ReportLab; normal replay
uses only the measured package and the committed PDF. --src selects a checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    cases = json.loads((HERE / "conventions.json").read_text())
    pdf = HERE / "fixtures/conventions.pdf"
    if args.generate:
        from reportlab.pdfgen.canvas import Canvas

        canvas = Canvas(str(pdf), pagesize=(612, 792), invariant=True)
        canvas.setTitle("Spacing and punctuation are separate observations")
        canvas.setAuthor("Anton Soloviev")
        for case in cases:
            canvas.drawString(40, 750, "Authored control: " + case["id"])
            canvas.drawString(40, 700, "Total 60.000")
            for i, row in enumerate(case["rows"]):
                canvas.drawString(40, 660 - 30 * i, row)
            canvas.showPage()
        canvas.save()
    if args.src:
        sys.path.insert(0, str(args.src.resolve()))
    from pydantic import BaseModel

    import fieldproof
    from fieldproof.document.loader import load_pdf
    from fieldproof.document.model import Document
    from fieldproof.ground.values import number_styles
    from fieldproof.schemas import Evidenced
    from fieldproof.verify import verify

    class Amount(BaseModel):
        total: Evidenced[float]

    Amount.model_rebuild(_types_namespace={"Evidenced": Evidenced})
    package = Path(fieldproof.__file__).resolve().parent
    assert package.is_relative_to(args.src.resolve() if args.src else Path(sys.prefix).resolve())
    document = load_pdf(pdf)
    rows = []
    style_observations = []
    for i, case in enumerate(cases, 1):
        page = document.page(i)
        isolated = Document("isolated formatting control", [page])
        styles = sorted(number_styles(page.text))
        style_observations.append({"id": case["id"], "actual": styles, "expected": case["styles"]})
        claims = [
            (value, "Total 60.000", expected)
            for value, expected in zip([60, 60000], case["total_statuses"], strict=True)
        ]
        if case.get("component"):
            claims.append((1234.5, case["rows"][0], "needs_review"))
        for value, quote, expected in claims:
            (field,) = verify(Amount(total={"value": value, "evidence": [quote]}), isolated).fields
            rows.append(
                {
                    "id": case["id"],
                    "page": i,
                    "value": value,
                    "quote": quote,
                    "expected": expected,
                    "status": field.status.value,
                    "reasons": field.reasons,
                    "matched_text": field.matched_text,
                    "rects": field.rects,
                }
            )
    failures = [r for r in rows if r["status"] != r["expected"]]
    style_failures = [r for r in style_observations if r["actual"] != r["expected"]]
    output = {
        "scope": "Six independent authored PDF controls; no model/OCR accuracy claim.",
        "packages": {
            name: version(name) for name in ["fieldproof", "pdfplumber", "pypdfium2", "pydantic"]
        },
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "cases_sha256": hashlib.sha256((HERE / "conventions.json").read_bytes()).hexdigest(),
        "source_sha256": {
            str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(package.rglob("*.py"))
        },
        "style_observations": style_observations,
        "style_mismatches": len(style_failures),
        "claims": rows,
        "claim_mismatches": len(failures),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(
        f"{len(rows)} claims: {len(failures)} unexpected verdicts; "
        f"{len(style_failures)} lost/conflicting convention observations"
    )
    if not args.observe_only:
        assert not failures and not style_failures


if __name__ == "__main__":
    main()
