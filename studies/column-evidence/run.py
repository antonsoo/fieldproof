"""Controlled native-PDF table layouts, with assignments known from drawing commands.

Synthetic data, no model/OCR and no claim of real-document accuracy.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from io import BytesIO
from pathlib import Path

FIELDS = ("description", "quantity", "unit_price", "amount")
LABELS = dict(zip(FIELDS, ("Description", "Qty", "Unit price", "Amount"), strict=True))


def make_case(order=FIELDS, align="left", swapped=False, broad=False, variant="plain"):
    from reportlab.pdfgen.canvas import Canvas

    buf = BytesIO()
    c = Canvas(buf, pagesize=(612, 792), invariant=True)
    c.setTitle("Synthetic column-association invoice")
    c.setAuthor("Fieldproof constructed layout study")
    for y, text in [
        (750, "Example Dispatch"),
        (725, "Invoice COL-12"),
        (700, "Issue Date: October 12, 2026"),
    ]:
        c.drawString(48, y, text)
    positions = dict(zip(order, (90, 245, 390, 545), strict=True))
    labels = LABELS.copy()
    if variant == "aliases":
        labels.update(description="Item description", quantity="Quantity", amount="Line total")
    if variant == "ambiguous_price":
        labels["unit_price"] = "Price"
    if variant == "missing_amount":
        labels.pop("amount")
    if variant == "duplicate_label":
        labels["unit_price"] = "Qty"
    if variant == "uppercase":
        labels = {k: v.upper() for k, v in labels.items()}
    draw = {"left": c.drawString, "center": c.drawCentredString, "right": c.drawRightString}[align]
    c.setFont("Helvetica-Bold", 10)
    if variant != "no_headers":
        for name, label in labels.items():
            draw(positions[name], 650, label)
    if variant == "previous_page":
        c.showPage()
    if variant == "intervening_prose":
        c.setFont("Helvetica", 12)
        c.drawString(48, 632, "Other charges follow in a different layout")
    printed = {"description": "Delivery", "quantity": "3", "unit_price": "12.50", "amount": "37.50"}
    if variant == "equal_numbers":
        printed.update(unit_price="3.00", amount="9.00")
    if variant == "header_gap":
        # No extrapolation from centers: the quantity lies entirely in a header gap.
        positions["quantity"] += 70
    c.setFont("Helvetica", 12)
    for name in order:
        draw(positions[name], 615, printed[name])
    c.drawString(48, 560, "Subtotal " + printed["amount"])
    c.drawString(48, 535, "Tax 0.00")
    c.drawString(48, 510, "Total " + printed["amount"])
    c.setFont("Helvetica", 9)
    c.drawString(48, 60, "Synthetic example. No transaction or model output.")
    c.save()

    page = 2 if variant == "previous_page" else 1

    def e(value, quote, p=page):
        return {"value": value, "evidence": [quote], "page": p}

    whole = " ".join(printed[name] for name in order)
    quantity = "unit_price" if swapped else "quantity"
    price = "quantity" if swapped else "unit_price"
    data = {
        "vendor_name": e("Example Dispatch", "Example Dispatch", 1),
        "invoice_number": e("COL-12", "Invoice COL-12", 1),
        "issue_date": e("2026-10-12", "Issue Date: October 12, 2026", 1),
        "line_items": [
            {
                "description": e("Delivery", "Delivery"),
                "quantity": e(float(printed[quantity]), whole if broad else printed[quantity]),
                "unit_price": e(float(printed[price]), whole if broad else printed[price]),
                "amount": e(float(printed["amount"]), whole),
            }
        ],
        "subtotal": e(float(printed["amount"]), "Subtotal " + printed["amount"]),
        "tax": e(0, "Tax 0.00"),
        "total": e(float(printed["amount"]), "Total " + printed["amount"]),
    }
    return buf.getvalue(), data


def cases():
    for order, align, swapped, broad in itertools.product(
        itertools.permutations(FIELDS), ("left", "center", "right"), (False, True), (False, True)
    ):
        yield {
            "id": "-".join(str(FIELDS.index(name)) for name in order)
            + f"-{align}-"
            + ("swapped" if swapped else "correct")
            + ("-row" if broad else "-token"),
            "order": order,
            "align": align,
            "swapped": swapped,
            "broad": broad,
        }
    for variant in (
        "aliases",
        "uppercase",
        "no_headers",
        "ambiguous_price",
        "missing_amount",
        "duplicate_label",
        "previous_page",
        "intervening_prose",
        "equal_numbers",
        "header_gap",
    ):
        for swapped in (False, True):
            yield {
                "id": variant + ("-swapped" if swapped else "-correct"),
                "variant": variant,
                "swapped": swapped,
                "broad": True,
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    if args.src:
        sys.path.insert(0, str(args.src.resolve()))
    import fieldproof
    from fieldproof.document.loader import load_pdf
    from fieldproof.schemas import Invoice
    from fieldproof.verify import verify

    if args.src:
        assert Path(fieldproof.__file__).resolve().is_relative_to(args.src.resolve())
    else:
        assert Path(fieldproof.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    args.out.mkdir(parents=True, exist_ok=True)
    records = []
    for case in cases():
        case = dict(case)
        name = case.pop("id")
        pdf, data = make_case(**case)
        report = verify(Invoice.model_validate(data), load_pdf(pdf)).to_dict()
        fields = {
            f["path"].rsplit(".", 1)[-1]: f
            for f in report["fields"]
            if f["path"].startswith("line_items")
        }
        variant = case.get("variant", "plain")
        resolved = variant in ("plain", "aliases", "uppercase")
        expected = "needs_review" if resolved and case["swapped"] else "verified"
        if not args.observe_only:
            assert fields["quantity"]["status"] == fields["unit_price"]["status"] == expected, (
                name,
                fields,
            )
            checks = report["column_checks"]
            assert len(checks) == 3
            if resolved:
                assert [c["status"] for c in checks] == (
                    ["contradictory"] * 2 + ["aligned"] if case["swapped"] else ["aligned"] * 3
                ), (name, checks)
            else:
                assert checks[0]["status"] == checks[1]["status"] == "unavailable", (name, checks)
        # Arithmetic is an independent ledger even when assignment is contradicted.
        assert report["cross_field_checks"][0]["status"] == "passed", name
        records.append(
            {
                "id": name,
                "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                "input_sha256": hashlib.sha256(
                    json.dumps(data, sort_keys=True).encode()
                ).hexdigest(),
                "fields": {
                    k: {
                        "status": f["status"],
                        "matched_text": f["matched_text"],
                        "rects": f["rects"],
                    }
                    for k, f in fields.items()
                },
                "column_statuses": [c["status"] for c in report.get("column_checks", [])],
                "arithmetic_sha256": hashlib.sha256(
                    json.dumps(report["cross_field_checks"], sort_keys=True).encode()
                ).hexdigest(),
                "line_extension": report["cross_field_checks"][0]["status"],
            }
        )
        if name in (
            "0-1-2-3-left-swapped-token",
            "0-1-2-3-left-correct-row",
            "equal_numbers-correct",
            "no_headers-swapped",
        ):
            (args.out / (name + ".pdf")).write_bytes(pdf)
            (args.out / (name + ".fixture.json")).write_text(
                json.dumps(
                    {
                        "schema": "invoice",
                        "provider": "fixture",
                        "model": "synthetic column evidence",
                        "data": data,
                    },
                    indent=2,
                )
                + "\n"
            )
            (args.out / (name + ".report.json")).write_text(json.dumps(report, indent=2) + "\n")
    (args.out / "cases.json").write_text(
        "[\n" + ",\n".join(json.dumps(record) for record in records) + "\n]\n"
    )
    print(
        json.dumps(
            {
                "cases": len(records),
                "reviewed_numeric_fields": sum(
                    f["status"] == "needs_review"
                    for r in records
                    for n, f in r["fields"].items()
                    if n in ("quantity", "unit_price")
                ),
                "origin": str(fieldproof.__file__),
            }
        )
    )


if __name__ == "__main__":
    main()
