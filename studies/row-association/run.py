"""Replay constructed PDFs through built-in schemas, retaining known limits too."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from io import BytesIO
from pathlib import Path

CASES = [
    {
        "id": "unique_other_row",
        "pages": [[(700, "Delivery 3 90.00"), (670, "Packing 2 15.00")]],
        "kind": "misassigned",
        "expect": "needs_review",
    },
    {
        "id": "unique_other_page",
        "pages": [[(700, "Delivery 3 90.00")], [(700, "Packing 2 15.00")]],
        "kind": "misassigned",
        "expect": "needs_review",
    },
    {
        "id": "receipt_other_row",
        "schema": "receipt",
        "pages": [[(700, "Delivery 3 90.00"), (670, "Packing 2 15.00")]],
        "kind": "misassigned",
        "expect": "needs_review",
    },
    {
        "id": "wrong_description",
        "description_quote": "Packing",
        "pages": [[(700, "Delivery 3 90.00"), (670, "Packing 2 15.00")]],
        "kind": "misassigned",
        "expect": "needs_review",
    },
    {
        "id": "missing_description",
        "description_quote": None,
        "pages": [[(700, "Delivery 3 90.00"), (670, "Packing 2 15.00")]],
        "kind": "misassigned",
        "expect": "needs_review",
    },
    {
        "id": "correct_one_line",
        "pages": [[(700, "Delivery 2 90.00"), (670, "Packing 3 15.00")]],
        "kind": "correct",
        "expect": "verified",
    },
    {
        "id": "correct_receipt",
        "schema": "receipt",
        "pages": [[(700, "Delivery 2 90.00"), (670, "Packing 3 15.00")]],
        "kind": "correct",
        "expect": "verified",
    },
    {
        "id": "correct_wrapped",
        "pages": [[(700, "Delivery"), (686, "2 90.00")]],
        "kind": "correct_but_layout_unresolved",
        "expect": "needs_review",
    },
    {
        "id": "wrong_column_same_line",
        "quantity_quote": "2.00",
        "pages": [[(700, "Delivery 3 2.00 6.00")]],
        "amount": 6,
        "amount_quote": "6.00",
        "kind": "known_semantic_limit",
        "expect": "verified",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    src = args.src.resolve()
    sys.path.insert(0, str(src))

    from reportlab.pdfgen.canvas import Canvas

    import fieldproof
    from fieldproof.document.loader import load_pdf
    from fieldproof.schemas import Invoice, Receipt
    from fieldproof.verify import verify

    assert Path(fieldproof.__file__).resolve().is_relative_to(src)
    args.out.mkdir(parents=True, exist_ok=True)
    results = []
    for case in CASES:
        stream = BytesIO()
        canvas = Canvas(stream, pagesize=(612, 792), invariant=True)
        for lines in case["pages"]:
            for y, text in lines:
                canvas.drawString(50, y, text)
            canvas.showPage()
        canvas.save()
        pdf = stream.getvalue()
        (args.out / f"{case['id']}.pdf").write_bytes(pdf)

        def e(value: str | float, quote: str | None = None) -> dict:
            return {"value": value, "evidence": [quote] if quote is not None else []}

        row = {
            "description": e("Delivery", case.get("description_quote", "Delivery")),
            "quantity": e(2, case.get("quantity_quote", "2")),
            "amount": e(case.get("amount", 90), case.get("amount_quote", "90.00")),
        }
        if case.get("schema") == "receipt":
            schema = Receipt
            data = {
                "merchant_name": e("Example"),
                "transaction_date": e("2026-10-09"),
                "total": e(105),
                "items": [row],
            }
            quantity_path = "items[0].quantity"
        else:
            schema = Invoice
            data = {
                "vendor_name": e("Example"),
                "invoice_number": e("ROW-TEST"),
                "issue_date": e("2026-10-09"),
                "total": e(105),
                "line_items": [row],
            }
            quantity_path = "line_items[0].quantity"
        report = verify(schema.model_validate(data), load_pdf(pdf))
        result = next(field for field in report.fields if field.path == quantity_path)
        agrees = result.status == case["expect"]
        results.append(
            {
                **case,
                "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                "quantity": result.to_dict(),
                "report": report.to_dict(),
                "agrees": agrees,
            }
        )
    summary = {
        "scope": "Constructed PDFs, no model; includes a known wrong-column limitation.",
        "source_sha256": {
            str(p.relative_to(src)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((src / "fieldproof").rglob("*.py"))
        },
        "cases": len(results),
        "disagreements": [r["id"] for r in results if not r["agrees"]],
        "remaining_verified_misassignments": [
            r["id"]
            for r in results
            if r["kind"] in ("misassigned", "known_semantic_limit")
            and r["quantity"]["status"] == "verified"
        ],
        "results": results,
    }
    (args.out / "observations.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("results", "source_sha256")}))
    if not args.observe_only:
        assert not summary["disagreements"]


if __name__ == "__main__":
    main()
