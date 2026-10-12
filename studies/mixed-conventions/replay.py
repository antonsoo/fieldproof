"""Reproduce conflicting conventions through actual PDF text, locations and reports.

Every document and claim is synthetic. Expectations are declared independently
of the inference helpers. --baseline records disagreements instead of failing.
Omit --source to check a separately installed wheel.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from io import BytesIO
from pathlib import Path

CONTEXTS = [
    ("absent", [], [], []),
    ("us", [(1, "US amount: 1,234.50"), (1, "US date: 12/31/2026")], ["decimal"], ["mdy"]),
    ("european", [(1, "EU amount: 1.234,50"), (1, "EU date: 31/12/2026")], ["thousands"], ["dmy"]),
    (
        "mixed-numbers",
        [(1, "US amount: 1,234.50"), (1, "EU amount: 1.234,50"), (1, "US date: 12/31/2026")],
        ["decimal", "thousands"],
        ["mdy"],
    ),
    (
        "mixed-dates",
        [(1, "EU amount: 1.234,50"), (1, "US date: 12/31/2026"), (1, "EU date: 31/12/2026")],
        ["thousands"],
        ["mdy", "dmy"],
    ),
    (
        "mixed-both",
        [
            (1, "US amount: 1,234.50"),
            (1, "EU amount: 1.234,50"),
            (1, "US date: 12/31/2026"),
            (1, "EU date: 31/12/2026"),
        ],
        ["decimal", "thousands"],
        ["mdy", "dmy"],
    ),
    (
        "mixed-reversed",
        [
            (1, "EU date: 31/12/2026"),
            (1, "US date: 12/31/2026"),
            (1, "EU amount: 1.234,50"),
            (1, "US amount: 1,234.50"),
        ],
        ["decimal", "thousands"],
        ["mdy", "dmy"],
    ),
    (
        "mixed-pages",
        [
            (1, "US amount: 1,234.50"),
            (1, "US date: 12/31/2026"),
            (2, "EU amount: 1.234,50"),
            (2, "EU date: 31/12/2026"),
        ],
        ["decimal", "thousands"],
        ["mdy", "dmy"],
    ),
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pdf-dir", type=Path, required=True)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument(
        "--reuse-pdfs",
        action="store_true",
        help="Read the exact existing PDF bytes instead of generating them.",
    )
    args = parser.parse_args()
    if args.source:
        sys.path.insert(0, str(args.source.resolve() / "src"))
    from pydantic import BaseModel
    from reportlab.pdfgen.canvas import Canvas

    from fieldproof.document.loader import load_pdf
    from fieldproof.schemas import Evidenced
    from fieldproof.verify import engine

    class Claims(BaseModel):
        total: Evidenced[float]
        issue_date: Evidenced[str]
        explicit_amount: Evidenced[float]
        explicit_date: Evidenced[str]

    Claims.model_rebuild(_types_namespace={"Evidenced": Evidenced})
    args.pdf_dir.mkdir(parents=True, exist_ok=True)
    records, documents = [], []
    for name, contexts, styles, orders in CONTEXTS:
        if args.reuse_pdfs:
            pdf = (args.pdf_dir / f"{name}.pdf").read_bytes()
        else:
            stream = BytesIO()
            canvas = Canvas(stream, pagesize=(612, 792), invariant=True)
            canvas.setTitle(f"Synthetic convention example: {name}")
            for page in range(1, max([1, *[p for p, _ in contexts]]) + 1):
                lines = [f"SYNTHETIC CONVENTION EXAMPLE: {name}"]
                if page == 1:
                    lines += [
                        "Total: 60.000",
                        "Issue date: 03/04/2026",
                        "Explicit amount: 17.50",
                        "Explicit date: 2026-06-18",
                    ]
                lines += [text for p, text in contexts if p == page]
                for index, line in enumerate(lines):
                    canvas.drawString(40, 740 - index * 32, line)
                canvas.showPage()
            canvas.save()
            pdf = stream.getvalue()
            (args.pdf_dir / f"{name}.pdf").write_bytes(pdf)
        document = load_pdf(pdf)
        documents.append(
            {
                "case": name,
                "bytes": len(pdf),
                "sha256": digest(pdf),
                "pages": len(document.pages),
                "declaredStyles": styles,
                "declaredOrders": orders,
            }
        )
        for style in (None, "decimal", "thousands"):
            for order in (None, "mdy", "dmy"):
                selected_style = styles[0] if len(styles) == 1 else style if not styles else None
                selected_order = orders[0] if len(orders) == 1 else order if not orders else None
                for amount, date, amount_style, date_order in [
                    (60.0, "2026-03-04", "decimal", "mdy"),
                    (60000.0, "2026-04-03", "thousands", "dmy"),
                ]:
                    claims = Claims(
                        total=Evidenced(value=amount, evidence=["Total: 60.000"], page=1),
                        issue_date=Evidenced(
                            value=date, evidence=["Issue date: 03/04/2026"], page=1
                        ),
                        explicit_amount=Evidenced(
                            value=17.5, evidence=["Explicit amount: 17.50"], page=1
                        ),
                        explicit_date=Evidenced(
                            value="2026-06-18", evidence=["Explicit date: 2026-06-18"], page=1
                        ),
                    )
                    expected = [
                        "verified" if selected_style == amount_style else "needs_review",
                        "verified" if selected_order == date_order else "needs_review",
                        "verified",
                        "verified",
                    ]
                    report = engine.verify(
                        claims, document, default_number_style=style, default_date_order=order
                    )
                    statuses = [f.status.value for f in report.fields]
                    assert all(f.page == 1 and f.rects for f in report.fields)
                    assert [f.matched_text for f in report.fields] == [
                        "Total: 60.000",
                        "Issue date: 03/04/2026",
                        "Explicit amount: 17.50",
                        "Explicit date: 2026-06-18",
                    ]
                    record = {
                        "case": name,
                        "numberDefault": style,
                        "dateDefault": order,
                        "amount": amount,
                        "date": date,
                        "expected": expected,
                        "matchesExpected": statuses == expected,
                        "report": report.to_dict(),
                    }
                    if not args.baseline:
                        assert record["matchesExpected"], (
                            name,
                            style,
                            order,
                            amount,
                            date,
                            statuses,
                        )
                    records.append(record)
    report = {
        "python": platform.python_version(),
        "driverSha256": digest(Path(__file__).read_bytes()),
        "engineSha256": digest(Path(engine.__file__).read_bytes()),
        "documents": documents,
        "reports": len(records),
        "fieldDecisions": sum(len(r["report"]["fields"]) for r in records),
        "matchingReports": sum(r["matchesExpected"] for r in records),
        "incorrectlyVerified": sum(
            f["status"] == "verified" and expected != "verified"
            for r in records
            for f, expected in zip(r["report"]["fields"], r["expected"], strict=True)
        ),
        "records": records,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"{report['matchingReports']}/{len(records)} reports match expectations; "
        f"{report['incorrectlyVerified']} ambiguous claims verified despite conflicting conventions"
    )


if __name__ == "__main__":
    main()
