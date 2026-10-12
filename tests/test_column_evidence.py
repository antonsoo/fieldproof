"""Column roles can contradict supported numbers even when arithmetic passes."""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest
from pydantic import BaseModel
from reportlab.pdfgen.canvas import Canvas

from fieldproof.document.loader import load_pdf
from fieldproof.document.model import BBox, Document
from fieldproof.schemas import Invoice
from fieldproof.verify import RowEvidenceRule, verify


def specimen(*, swapped: bool = False, broad: bool = False, rows: int = 1):
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=(612, 792), invariant=True)
    for x, label in [(48, "Description"), (310, "Qty"), (400, "Unit price"), (510, "Amount")]:
        canvas.drawString(x, 700, label)
    items = []

    def e(value, quote):
        return {"value": value, "evidence": [quote]}

    for i in range(rows):
        label = f"Delivery-{chr(65 + i)}"
        qty, price = 3 + i, 12.5 + i
        text = [label, str(qty), f"{price:.2f}", f"{qty * price:.2f}"]
        for x, value in zip((48, 310, 400, 510), text, strict=True):
            canvas.drawString(x, 670 - 22 * i, value)
        whole = " ".join(text)
        items.append(
            {
                "description": e(label, label),
                "quantity": e(
                    price if swapped else qty, whole if broad else text[2 if swapped else 1]
                ),
                "unit_price": e(
                    qty if swapped else price, whole if broad else text[1 if swapped else 2]
                ),
                "amount": e(qty * price, whole),
            }
        )
    canvas.save()
    data = Invoice.model_validate(
        {
            "vendor_name": e("Example", "Example"),
            "invoice_number": e("COL", "COL"),
            "issue_date": e("2026-10-12", "2026-10-12"),
            "total": e(37.5, "37.50"),
            "line_items": items,
        }
    )
    return data, load_pdf(stream.getvalue())


@pytest.mark.parametrize("broad", [False, True])
def test_swap_retains_quote_geometry_and_passing_arithmetic(broad):
    data, document = specimen(swapped=True, broad=broad, rows=3)
    report = verify(data, document)
    numeric = [f for f in report.fields if f.path.endswith((".quantity", ".unit_price"))]
    assert all(f.status == "needs_review" and f.rects for f in numeric)
    assert all("column association" in f.reasons[-1] for f in numeric)
    assert [c.status for c in report.column_checks] == [
        "contradictory",
        "contradictory",
        "aligned",
    ] * 3
    assert all(
        c.status == "passed"
        for c in report.cross_field_checks
        if c.rule == "invoice.line_extension"
    )
    check = report.column_checks[0]
    assert check.observed_column == "unit_price"
    assert check.headers["quantity"]["text"] == "Qty"
    assert check.value_locations[0]["text"] == "12.50"
    disabled = verify(data, document, row_rules=[])
    assert disabled.column_checks == []
    before = next(f for f in disabled.fields if f.path == check.field)
    after = next(f for f in report.fields if f.path == check.field)
    assert before.status == "verified" and before.rects == after.rects


def test_correct_rows_and_header_lifetime():
    data, document = specimen(rows=3)
    assert all(c.status == "aligned" for c in verify(data, document).column_checks)
    # A page edit must never reuse a prior verification's layout cache.
    page = document.pages[0]
    document.pages[0] = replace(page, words=[w for w in page.words if w.bbox.top > 90])
    assert all(c.status == "unavailable" for c in verify(data, document).column_checks)


@pytest.mark.parametrize("box", [BBox(0, 0, 0, 10), BBox(float("nan"), 0, 10, 10)])
def test_unusable_geometry_does_not_remove_a_table_barrier(box):
    data, doc = specimen()
    page = doc.pages[0]
    page.words[0] = replace(page.words[0], bbox=box)
    assert all(c.status == "unavailable" for c in verify(data, doc).column_checks)


def test_custom_headers_and_nested_collection_are_explicit():
    data, doc = specimen(swapped=True)

    class Form(BaseModel):
        invoice: Invoice

    wrapped = Form(invoice=data)
    rule = RowEvidenceRule(
        "invoice.line_items",
        "description",
        ("quantity", "unit_price", "amount"),
        column_headers={
            "description": ("Description",),
            "quantity": ("Qty",),
            "unit_price": ("Unit price",),
            "amount": ("Amount",),
        },
    )
    report = verify(wrapped, doc, row_rules=[rule])
    assert report.column_checks[0].field == "invoice.line_items[0].quantity"
    assert report.column_checks[0].status == "contradictory"
    assert verify(wrapped, doc).column_checks == []


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"description": ("Description",)},
        {"description": ("Description",), "quantity": "Qty"},
        {"description": ("Description",), "quantity": ("  ",)},
        {"description": ("Qty",), "quantity": ("qty",)},
    ],
)
def test_invalid_header_configuration_is_rejected(headers):
    with pytest.raises(ValueError):
        RowEvidenceRule("rows", "description", ("quantity",), column_headers=headers)


def test_empty_documents_and_absent_fields_have_explicit_unavailable_evidence():
    data, _ = specimen()
    data.line_items[0].quantity = None
    report = verify(data, Document("empty"))
    assert len(report.column_checks) == 3
    assert all(c.status == "unavailable" for c in report.column_checks)
    assert "line_items[0].quantity" not in {f.path for f in report.fields}
