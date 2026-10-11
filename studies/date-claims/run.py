"""Replay synthetic extracted date claims against an actual PDF and invoice audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from io import BytesIO
from pathlib import Path

CASES = [
    ("canonical", "2026-03-04", "2026-03-05", "verified", "verified", "passed"),
    ("negated-issue", "not 2026-03-04", "2026-03-05", "needs_review", "verified", "not_checked"),
    (
        "alternative-issue",
        "2026-03-04 or 2026-04-03",
        "2026-03-05",
        "needs_review",
        "verified",
        "not_checked",
    ),
    ("labeled-claim", "Issue: 2026-03-04", "2026-03-05", "needs_review", "verified", "not_checked"),
    ("ambiguous-claim", "03/04/2026", "2026-03-05", "needs_review", "verified", "not_checked"),
    ("written-claim", "March 4, 2026", "2026-03-05", "needs_review", "verified", "not_checked"),
    ("unpadded-claim", "2026-3-4", "2026-03-05", "needs_review", "verified", "not_checked"),
    ("invalid-calendar", "2026-02-29", "2026-03-05", "needs_review", "verified", "not_checked"),
    ("wrong-canonical-date", "2026-04-03", "2026-03-05", "needs_review", "needs_review", "failed"),
    ("negated-due", "2026-03-04", "not 2026-03-05", "verified", "needs_review", "not_checked"),
    (
        "alternative-due",
        "2026-03-04",
        "2026-03-05 or 2026-03-06",
        "verified",
        "needs_review",
        "not_checked",
    ),
    ("ambiguous-due", "2026-03-04", "03/05/2026", "verified", "needs_review", "not_checked"),
]


def fixture(issue: str, due: str) -> dict:
    def field(value, quote):
        return {"value": value, "evidence": [quote], "page": 1}

    return {
        "schema": "invoice",
        "model": "synthetic-date-claims",
        "data": {
            "vendor_name": field("Example Workshop", "Example Workshop"),
            "invoice_number": field("DATE-001", "Invoice: DATE-001"),
            "issue_date": field(issue, "Issue date: 2026-03-04"),
            "due_date": field(due, "Due date: 2026-03-05"),
            "total": field(10.0, "Total: $10.00"),
            "line_items": [],
        },
    }


def make_pdf() -> bytes:
    from reportlab.pdfgen.canvas import Canvas

    output = BytesIO()
    canvas = Canvas(output, pagesize=(612, 792), invariant=True)
    canvas.setAuthor("Fieldproof verification fixtures")
    canvas.setTitle("Synthetic extracted date claims")
    canvas.setFont("Helvetica-Bold", 18)
    canvas.drawString(42, 740, "Example Workshop")
    canvas.setFont("Helvetica", 12)
    for index, text in enumerate(
        ["Invoice: DATE-001", "Issue date: 2026-03-04", "Due date: 2026-03-05", "Total: $10.00"]
    ):
        canvas.drawString(42, 690 - index * 30, text)
    canvas.setFont("Helvetica", 9)
    canvas.drawString(42, 50, "Synthetic fixture. The extraction claims are deliberately varied.")
    canvas.save()
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    if args.src:
        sys.path.insert(0, str(args.src.resolve()))
    import fieldproof
    from fieldproof.document.loader import load_pdf
    from fieldproof.schemas.invoice import Invoice
    from fieldproof.verify import verify

    root = Path(__file__).resolve().parent
    pdf = make_pdf()
    path = root / "date-claims.pdf"
    if path.exists():
        assert path.read_bytes() == pdf
    else:
        path.write_bytes(pdf)
    document = load_pdf(pdf)
    results = []
    for name, issue, due, issue_status, due_status, chronology in CASES:
        data = Invoice.model_validate(fixture(issue, due)["data"])
        for default in (None, "mdy", "dmy"):
            report = verify(data, document, default_date_order=default)
            fields = {
                f.path: f.to_dict() for f in report.fields if f.path in ("issue_date", "due_date")
            }
            check = next(
                c.to_dict() for c in report.cross_field_checks if c.rule == "invoice.due_date_order"
            )
            assert fields["issue_date"]["value"] == issue and fields["due_date"]["value"] == due
            for field in fields.values():
                assert field["page"] == 1 and field["rects"] and field["match_score"] == 100
            actual = [fields["issue_date"]["status"], fields["due_date"]["status"], check["status"]]
            expected = [issue_status, due_status, chronology]
            results.append(
                {
                    "case": name,
                    "date_order": default,
                    "expected": expected,
                    "actual": actual,
                    "agrees": actual == expected,
                    "fields": fields,
                    "date_check": check,
                }
            )
    receipt = {
        "python": platform.python_version(),
        "package_version": fieldproof.__version__,
        "scope": (
            "Synthetic PDF and extraction claims; no model calls. "
            "All original claims and geometry retained."
        ),
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "cases": len(results),
        "disagreements": sum(not r["agrees"] for r in results),
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"{receipt['cases']} cases, {receipt['disagreements']} disagreements")
    if not args.observe_only and receipt["disagreements"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
