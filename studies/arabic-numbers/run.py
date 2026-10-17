"""Replay native locale numbers through an actual PDF, quote aligner and verifier.

Use --src to compare another checkout; omit it to verify an installed wheel.
--observe-only retains an old implementation's verdicts without asserting success.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from collections import Counter
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent
WRONG = {
    "grouped": [1, 234, 56],
    "decimal": [1, 25],
    "million": [1, 234, 567, 89],
    "integer": [1, 234],
    "negative": [-1, 234, 56],
    "large-integer": [9, 7, 199, 254, 740, 993],
    "percent": [12, 5, 12.5],
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    if args.src:
        sys.path.insert(0, str(args.src.resolve()))

    from pydantic import BaseModel

    import fieldproof
    from fieldproof.document.loader import load_pdf
    from fieldproof.schemas import Evidenced
    from fieldproof.verify.engine import verify

    class Amount(BaseModel):
        total: Evidenced[float]

    class IntegerAmount(BaseModel):
        total: Evidenced[int]

    Amount.model_rebuild(_types_namespace={"Evidenced": Evidenced})
    IntegerAmount.model_rebuild(_types_namespace={"Evidenced": Evidenced})
    package = Path(fieldproof.__file__).resolve().parent
    if args.src:
        assert package.is_relative_to(args.src.resolve())
    fixture = HERE / "fixtures/numbers.pdf"
    intl = json.loads((HERE / "intl.json").read_text())
    document = load_pdf(fixture)
    rows = []
    for page, case in enumerate(intl["cases"], 1):
        quote = case["id"] + " total: " + case["numericText"]
        assert document.page(page).text.endswith(quote)
        correct = int(case["input"]) if case.get("integer") else float(case["input"])
        claims = [("correct", correct, "verified")] if not case.get("percent") else []
        claims += [
            ("fragment", value, "needs_review") for value in WRONG[case["id"].split("-", 1)[1]]
        ]
        schema = IntegerAmount if case.get("integer") else Amount
        for kind, value, expected in claims:
            data = schema.model_validate(
                {"total": {"value": value, "evidence": [quote], "page": page}}
            )
            (result,) = verify(data, document).fields
            rows.append(
                {
                    "id": case["id"],
                    "kind": kind,
                    "page": page,
                    "quote": quote,
                    "value": value,
                    "expected": expected,
                    "result": result.to_dict(),
                    "agrees": result.status.value == expected,
                }
            )
        # The expectation comes from the formatter's input, never its rendered fragments.
        if not case.get("percent"):
            assert Decimal(str(correct)) == Decimal(case["input"])
    mismatches = [f"{r['id']}:{r['kind']}:{r['value']}" for r in rows if not r["agrees"]]
    output = {
        "scope": (
            "Controlled native Intl strings in an authored PDF; "
            "no model, OCR or real-invoice accuracy measurement."
        ),
        "python": platform.python_version(),
        "packages": {
            name: version(name) for name in ("fieldproof", "pdfplumber", "pypdfium2", "pydantic")
        },
        "pdf_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "intl_sha256": hashlib.sha256((HERE / "intl.json").read_bytes()).hexdigest(),
        "source_sha256": {
            str(path.relative_to(package)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(package.rglob("*.py"))
        },
        "verdicts": dict(Counter(r["result"]["status"] for r in rows)),
        "mismatches": mismatches,
        "claims": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(
        f"{len(rows)} claims across {len(intl['cases'])} PDF pages: "
        f"{len(mismatches)} unexpected verdicts; {output['verdicts']}"
    )
    if mismatches and not args.observe_only:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
