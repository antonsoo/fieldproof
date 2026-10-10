"""Replay explicit Boolean answers and misleading prose through actual PDF grounding.

Expectations are hand-labelled, synthetic controls, not extraction-accuracy data.
Use --src for a source checkout; omit it to exercise the installed package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from io import BytesIO
from pathlib import Path

# An answer of None means this quote needs interpretation, not that its English
# meaning is unknown. Even correct guesses about prose must remain reviewable.
CASES: list[tuple[str, str, bool | None]] = [
    ("approved-not-denied", "The request is approved, not denied.", None),
    ("unrelated-no", "No changes: approval confirmed.", None),
    ("previous-denial", "Approval was denied previously, but is confirmed today.", None),
    ("not-only", "The request is not only approved but expedited.", None),
    ("positive-prose", "Approved in November, with notice given", None),
    ("negative-prose", "This agreement is not renewable", None),
    ("denied-status", "Status: denied", None),
    ("not-denied", "The request was not denied.", None),
    ("not-false", "The statement is not false.", None),
    ("future", "The request will be approved after review.", None),
    ("condition", "Approval: yes, pending signature", None),
    ("exception", "Approval: no (unless reviewed)", None),
    ("number-constraint", "No more than one signature is required.", None),
    ("choice-or", "Approval: yes or no", None),
    ("choice-slash", "Approval: yes/no", None),
    ("choice-label", "Yes/No: yes", None),
    ("two-answers", "Approved: yes; Renewal: no", None),
    ("question", "Approval: false?", None),
    ("checked-yes", "Approval: [x] yes [ ] no", None),
    ("checked-no", "Approval: [ ] yes [x] no", None),
    ("literal-yes", "yes", True),
    ("literal-no", "no", False),
    ("literal-true", "true", True),
    ("literal-false", "false", False),
    ("label-yes", "Approval: yes", True),
    ("label-no", "Approval: no", False),
    ("label-true", "Approval: true", True),
    ("label-false", "Approval: false", False),
    ("upper-equal", "APPROVAL = TRUE.", True),
    ("mixed-case", "Approval = False", False),
    ("confirmed-answer", "Confirmed: yes", True),
    ("renewal-answer", "Renewal: no", False),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pdf-dir", type=Path, required=True)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    if args.src:
        sys.path.insert(0, str(args.src.resolve()))

    from pydantic import BaseModel
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen.canvas import Canvas

    import fieldproof
    from fieldproof.document.loader import load_pdf
    from fieldproof.schemas import Evidenced
    from fieldproof.verify.engine import verify

    if args.src:
        assert Path(fieldproof.__file__).resolve().is_relative_to(args.src.resolve())

    class Approval(BaseModel):
        approved: Evidenced[bool]

    Approval.model_rebuild(_types_namespace={"Evidenced": Evidenced})
    args.pdf_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    sources = []
    for index, (name, quote, answer) in enumerate(CASES, 1):
        output = BytesIO()
        canvas = Canvas(output, pagesize=(612, 792), invariant=True)
        canvas.setTitle("Synthetic Boolean evidence case")
        canvas.setAuthor("Fieldproof verification fixtures")
        canvas.setFillColor(HexColor("#14524c"))
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(42, 748, "SYNTHETIC DOCUMENT / BOOLEAN EVIDENCE")
        canvas.setFillColor(HexColor("#182d2b"))
        canvas.setFont("Helvetica-Bold", 24)
        canvas.drawString(42, 695, "Purchase order approval")
        canvas.setFont("Helvetica", 12)
        canvas.drawString(42, 635, quote)
        canvas.setFont("Helvetica", 9)
        canvas.drawString(42, 55, f"Synthetic verification fixture. Case {index:02d}.")
        canvas.save()
        pdf = output.getvalue()
        path = args.pdf_dir / f"{name}.pdf"
        if path.exists():
            assert path.read_bytes() == pdf, f"regeneration changed {path.name}"
        else:
            path.write_bytes(pdf)
        sources.append(
            {"file": path.name, "bytes": len(pdf), "sha256": hashlib.sha256(pdf).hexdigest()}
        )
        document = load_pdf(pdf)
        for value in (False, True):
            report = verify(
                Approval(approved=Evidenced(value=value, evidence=[quote], page=1)), document
            )
            field = report.fields[0]
            expected = "verified" if value is answer else "needs_review"
            retained = field.to_dict()
            assert type(retained["value"]) is bool
            assert field.page == 1 and field.rects and field.match_score == 100, (name, retained)
            assert field.matched_text == quote, (name, field.matched_text)
            rows.append(
                {
                    "case": name,
                    "quote": quote,
                    "explicit_answer": answer,
                    "claim": value,
                    "expected_status": expected,
                    "passed": field.status.value == expected,
                    "field": retained,
                }
            )
    report = {
        "schema_version": 1,
        "python": platform.python_version(),
        "package_version": fieldproof.__version__,
        "module_source": "source checkout" if args.src else "installed package",
        "value_checks_sha256": hashlib.sha256(
            (Path(fieldproof.__file__).parent / "verify/value_checks.py").read_bytes()
        ).hexdigest(),
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "pdfs": sources,
        "cases": rows,
        "passed": sum(row["passed"] for row in rows),
        "total": len(rows),
        "located_quotes_and_rectangles_retained": len(rows),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"{report['passed']}/{report['total']} expected outcomes; "
        f"{len(rows)} located quotes with page rectangles retained"
    )
    if not args.observe_only and report["passed"] != report["total"]:
        raise SystemExit("Boolean replay failed; inspect retained report")


if __name__ == "__main__":
    main()
