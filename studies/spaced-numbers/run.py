"""Replay grouping ambiguity and real layout through the PDF loader and verifier."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from collections import Counter
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--observe-only", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    if args.src:
        sys.path.insert(0, str(args.src.resolve()))
    from pydantic import BaseModel

    import fieldproof
    from fieldproof.document.loader import load_pdf
    from fieldproof.document.model import Document
    from fieldproof.schemas import Evidenced
    from fieldproof.verify import verify

    class Amount(BaseModel):
        total: Evidenced[float]

    Amount.model_rebuild(_types_namespace={"Evidenced": Evidenced})
    package = Path(fieldproof.__file__).resolve().parent
    if args.src:
        assert package.is_relative_to(args.src.resolve())
    pdf = HERE / "fixtures/numbers.pdf"
    document = load_pdf(pdf)
    cases = json.loads((HERE / "cases.json").read_text())
    rows = []
    for page_number, case in enumerate(cases, 1):
        page = document.page(page_number)
        text = " ".join(case["text"].split())
        quote = text if case.get("layout") else "Total " + text
        assert page.text.endswith(quote), page.text
        claims: list[tuple[str, float, str, str]] = []
        if case.get("layout"):
            quantity_status = "verified" if case["layout"] == "wide-columns" else "needs_review"
            claims = [
                ("quantity", 1, quantity_status, quote),
                ("quantity-clipped", 1, quantity_status, "1"),
                ("price", 210.5, "verified", quote),
                ("invented-merge", 1210.5, "needs_review", quote),
            ]
        else:
            grouped = " " in text
            if case.get("input") is not None:
                correct = float(case["input"])
                claims.append(("whole", correct, "needs_review" if grouped else "verified", quote))
            fragments = [1, 234, 56, 234.56]
            if "million" in case["id"] or "1234567" in case["id"]:
                fragments += [567, 89, 567.89]
            for value in fragments:
                if str(value) != case.get("input"):
                    claims.append(("fragment", value, "needs_review", quote))
            if grouped and case["id"] != "rate":
                clipped = text.split()[-1].rstrip(")")
                claims.append(("clipped", 234.56, "needs_review", clipped))
        for kind, value, expected, evidence in claims:
            data = Amount(total={"value": value, "evidence": [evidence], "page": page_number})
            # Each page is an independent authored control. A page hint is not
            # permission to ignore duplicate quotes on other pages of a document.
            (result,) = verify(data, Document("isolated authored control", [page])).fields
            rows.append(
                {
                    "id": case["id"],
                    "kind": kind,
                    "page": page_number,
                    "value": value,
                    "quote": evidence,
                    "expected": expected,
                    "status": result.status.value,
                    "matched_text": result.matched_text,
                    "reasons": result.reasons,
                    "rects": result.rects,
                }
            )
    failures = [f"{r['id']}:{r['kind']}:{r['value']}" for r in rows if r["status"] != r["expected"]]
    ledger = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    output = {
        "scope": (
            "Authored native-text PDFs; grouping ambiguity is retained, not resolved by guessing. "
            "No model/OCR accuracy claim."
        ),
        "python": platform.python_version(),
        "packages": {
            name: version(name) for name in ["fieldproof", "pdfplumber", "pypdfium2", "pydantic"]
        },
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "cases_sha256": hashlib.sha256((HERE / "cases.json").read_bytes()).hexdigest(),
        "source_sha256": {
            str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(package.rglob("*.py"))
        },
        "claim_count": len(rows),
        "claims_sha256": hashlib.sha256(ledger.encode()).hexdigest(),
        "verdicts": dict(Counter(r["status"] for r in rows)),
        "mismatches": failures,
        **({} if args.summary_only else {"claims": rows}),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(
        f"{len(rows)} claims / {len(cases)} PDF pages: "
        f"{len(failures)} unexpected verdicts; {output['verdicts']}"
    )
    if failures and not args.observe_only:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
