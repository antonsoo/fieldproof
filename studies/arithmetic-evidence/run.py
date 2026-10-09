"""Replay controlled PDFs and an independent rational-arithmetic oracle.

Run this file with --src src --out /tmp/arithmetic (using the development environment).
Use --observe-only to retain behavior from the old source without enforcing new expectations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import sys
import time
from collections import Counter
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    from cases import cases, evidence, invoice, row

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    src = args.src.resolve()
    sys.path.insert(0, str(src))
    from reportlab.pdfgen.canvas import Canvas

    import fieldproof
    from fieldproof.document.loader import load_pdf
    from fieldproof.schemas import BUILTIN_SCHEMAS, iter_evidenced_fields
    from fieldproof.schemas.invoice import Invoice
    from fieldproof.verify.cross_field import check_invoice
    from fieldproof.verify.engine import verify

    assert Path(fieldproof.__file__).resolve().is_relative_to(src)
    args.out.mkdir(parents=True, exist_ok=True)

    results = []
    for case in cases():
        data = BUILTIN_SCHEMAS[case.get("schema", "invoice")].model_validate(case["data"])
        path = args.out / f"{case['id']}.pdf"
        canvas = Canvas(str(path), pagesize=(612, 792), invariant=True)
        canvas.setTitle(f"Synthetic arithmetic control: {case['id']}")
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(36, 757, f"SYNTHETIC ARITHMETIC CONTROL / {case['id']}")
        canvas.setFont("Helvetica", 10)
        for index, (field_path, value) in enumerate(iter_evidenced_fields(data)):
            # Money in a printed document uses decimal digits, not Python's 1e+16 display.
            printed = (
                format(Decimal(str(value.value)), "f")
                if isinstance(value.value, (int, float))
                else value.value
            )
            quote = f"{field_path}: {printed}"
            value.evidence = [quote]
            canvas.drawString(36, 724 - index * 26, quote)
        if case.get("note"):
            canvas.drawString(36, 120, case["note"])
        canvas.drawString(
            36, 60, "Hand-written claims and document. No real transaction or model output."
        )
        canvas.save()
        fixture = {
            "schema": case.get("schema", "invoice"),
            "provider": "fixture",
            "model": "synthetic arithmetic control",
            "data": data.model_dump(mode="json"),
        }
        (args.out / f"{case['id']}.json").write_text(json.dumps(fixture, indent=2) + "\n")
        report = verify(data, load_pdf(path), default_number_style="decimal")
        observed = sorted(field.path for field in report.fields if field.status.value != "verified")
        results.append(
            {
                "id": case["id"],
                "pdfSha256": digest(path),
                "expectedReview": sorted(case["review"]),
                "observedReview": observed,
                "agrees": observed == sorted(case["review"]),
                "report": report.to_dict(),
            }
        )

    # Independent integer/rational arithmetic. Source values are the actual validated
    # claims; calculations never use the checker's Decimal implementation or context.
    rng = random.Random(20261009)
    checks, disagreements = Counter(), []
    started = time.perf_counter()
    for index in range(2400):
        quantity = rng.randrange(-400, 401) / 8
        price = rng.randrange(0, 100000) / 100
        exact = Fraction(str(quantity)) * Fraction(str(price))
        amount = float(exact + Fraction(rng.choice([-3, -2, 0, 2, 3]), 100))
        data = Invoice.model_validate(
            invoice(
                line_items=[row(quantity, price, amount)],
                subtotal=evidence(amount),
                tax=evidence(0),
                total=evidence(amount),
            )
        )
        model_item = data.line_items[0]
        expected_product = Fraction(str(model_item.quantity.value)) * Fraction(
            str(model_item.unit_price.value)
        )
        difference = Fraction(str(model_item.amount.value)) - expected_product
        expected_failure = abs(difference) > Fraction(1, 50)
        issues = check_invoice(data)
        found = any("line_items[0].quantity" in issue.fields for issue in issues)
        agrees = found == expected_failure
        checks["expectedFailed" if expected_failure else "expectedPassed"] += 1
        if hasattr(fieldproof.verify.cross_field, "audit_invoice"):
            check = fieldproof.verify.cross_field.audit_invoice(data)[0]
            agrees &= (
                Fraction(check.computed) == expected_product
                and Fraction(check.difference) == difference
            )
        if not agrees:
            disagreements.append(
                {
                    "kind": "line_extension",
                    "index": index,
                    "quantity": quantity,
                    "unitPrice": price,
                    "amount": amount,
                    "expectedFailure": expected_failure,
                    "found": found,
                }
            )
    for kind in ["items_subtotal", "subtotal_tax_total"]:
        for index in range(1200):
            values = [rng.randrange(-100000, 100001) / 100 for _ in range(8)]
            if kind == "items_subtotal":
                if index % 3 == 0:
                    values = [1e16, *values, -1e16]
                exact = sum((Fraction(str(value)) for value in values), Fraction(0))
                observed = float(exact + Fraction(rng.choice([-3, -2, 0, 2, 3]), 100))
                data = Invoice.model_validate(
                    invoice(
                        line_items=[row(None, None, value) for value in values],
                        subtotal=evidence(observed),
                        tax=None,
                        total=evidence(observed),
                    )
                )
                expected = sum(
                    (Fraction(str(item.amount.value)) for item in data.line_items), Fraction(0)
                )
                actual = Fraction(str(data.subtotal.value))
                found = any("subtotal" in issue.fields for issue in check_invoice(data))
            else:
                subtotal, tax = (1e16 if index % 3 == 0 else values[0]), values[1]
                exact = Fraction(str(subtotal)) + Fraction(str(tax))
                observed = float(exact + Fraction(rng.choice([-3, -2, 0, 2, 3]), 100))
                data = Invoice.model_validate(
                    invoice(
                        line_items=[],
                        subtotal=evidence(subtotal),
                        tax=evidence(tax),
                        total=evidence(observed),
                    )
                )
                expected = Fraction(str(data.subtotal.value)) + Fraction(str(data.tax.value))
                actual = Fraction(str(data.total.value))
                found = any("tax" in issue.fields for issue in check_invoice(data))
            difference = actual - expected
            expected_failure = abs(difference) > Fraction(1, 50)
            agrees = found == expected_failure
            checks["expectedFailed" if expected_failure else "expectedPassed"] += 1
            if hasattr(fieldproof.verify.cross_field, "audit_invoice"):
                check = next(
                    c
                    for c in fieldproof.verify.cross_field.audit_invoice(data)
                    if c.rule == f"invoice.{kind}"
                )
                agrees &= (
                    Fraction(check.computed) == expected
                    and Fraction(check.difference) == difference
                )
            if not agrees:
                disagreements.append(
                    {
                        "kind": kind,
                        "index": index,
                        "inputs": values if kind == "items_subtotal" else [subtotal, tax],
                        "observed": observed,
                        "expectedFailure": expected_failure,
                        "found": found,
                    }
                )
    seconds = time.perf_counter() - started
    evidence_json = {
        "scope": (
            "Controlled PDFs and rational-arithmetic cases; no real transactions or model output."
        ),
        "python": platform.python_version(),
        "caseSourceSha256": digest(HERE / "cases.py"),
        "implementationSha256": digest(src / "fieldproof/verify/cross_field.py"),
        "pdfCases": results,
        "oracle": {"cases": 4800, **checks, "disagreements": disagreements, "seconds": seconds},
    }
    (args.out / "results.json").write_text(json.dumps(evidence_json, indent=2) + "\n")
    unexpected = [case["id"] for case in results if not case["agrees"]]
    print(
        json.dumps(
            {
                "pdfCases": len(results),
                "unexpectedPdfVerdicts": unexpected,
                "oracleCases": 4800,
                "oracleDisagreements": len(disagreements),
                "seconds": seconds,
            }
        )
    )
    if (unexpected or disagreements) and not args.observe_only:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
