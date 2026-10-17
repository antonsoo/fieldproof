"""Source support and an item's declared row relationship are separate evidence."""

from __future__ import annotations

from io import BytesIO

import pytest
from pydantic import BaseModel
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from fieldproof.document.loader import load_pdf
from fieldproof.document.model import Document
from fieldproof.schemas import Evidenced, Invoice, LineItem, Receipt
from fieldproof.schemas.receipt import ReceiptItem
from fieldproof.verify import RowEvidenceRule, verify


def document(*pages: list[tuple[float, str]]) -> Document:
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=(612, 792), invariant=True)
    for lines in pages:
        for y, text in lines:
            # These controls isolate row assignment using clear cells. A tight
            # single text run would also introduce quantity/grouping ambiguity.
            x = 50.0
            for cell in text.split():
                canvas.drawString(x, y, cell)
                x += stringWidth(cell, "Helvetica", 12) + 40
        canvas.showPage()
    canvas.save()
    return load_pdf(stream.getvalue())


def item() -> LineItem:
    return LineItem(
        description=Evidenced(value="Delivery", evidence=["Delivery"]),
        quantity=Evidenced(value=2, evidence=["2"]),
        amount=Evidenced(value=90, evidence=["90.00"]),
    )


def invoice(row: LineItem | None = None) -> Invoice:
    return Invoice(
        vendor_name=Evidenced(value="Example"),
        invoice_number=Evidenced(value="ROW-TEST"),
        issue_date=Evidenced(value="2026-10-09"),
        total=Evidenced(value=105),
        line_items=[row or item()],
    )


@pytest.mark.parametrize("other_page", [False, True])
def test_unique_but_misassigned_number_retains_both_source_locations(other_page: bool) -> None:
    lines = [(700, "Delivery 3 90.00")]
    donor = [(670, "Packing 2 15.00")]
    doc = document(lines, donor) if other_page else document(lines + donor)
    report = verify(invoice(), doc)
    quantity = next(f for f in report.fields if f.path == "line_items[0].quantity")
    assert quantity.status == "needs_review"
    assert quantity.matched_text == "2" and quantity.rects
    assert quantity.page == (2 if other_page else 1)
    check, missing_price, amount = report.row_checks
    assert check.status == "separate"
    assert check.field_source_status == check.anchor_source_status == "verified"
    assert check.field_location is not None and check.anchor_location is not None
    assert check.field_location["text"] == "2"
    assert check.anchor_location["text"] == "Delivery"
    assert "row association needs review" in quantity.reasons[0]
    assert missing_price.status == "unavailable" and missing_price.field_source_status is None
    assert amount.status == "same_line"
    assert next(f for f in report.fields if f.path == amount.field).status == "verified"


def test_receipt_uses_its_description_rule_by_default() -> None:
    receipt = Receipt(
        merchant_name=Evidenced(value="Example"),
        transaction_date=Evidenced(value="2026-10-09"),
        total=Evidenced(value=105),
        items=[ReceiptItem.model_validate(item().model_dump())],
    )
    report = verify(receipt, document([(700, "Delivery 3 90.00"), (670, "Packing 2 15.00")]))
    assert report.row_checks[0].field == "items[0].quantity"
    assert report.row_checks[0].status == "separate"
    assert next(f for f in report.fields if f.path == "items[0].quantity").status == "needs_review"


def test_a_wrapped_but_correct_row_is_honestly_sent_to_review() -> None:
    row = item()
    row.quantity = Evidenced(value=3, evidence=["3"])
    report = verify(invoice(row), document([(700, "Delivery"), (686, "3 90.00")]))
    quantity = next(f for f in report.fields if f.path.endswith(".quantity"))
    assert quantity.status == "needs_review"
    assert "wrapped table layout" in quantity.reasons[0]
    assert report.row_checks[0].field_source_status == "verified"


def test_uncertain_description_cannot_be_replaced_by_another_numeric_anchor() -> None:
    row = item()
    row.description = Evidenced(value="Delivery", evidence=["Packing"])
    row.unit_price = Evidenced(value=45, evidence=["45.00"])
    report = verify(
        invoice(row), document([(700, "Delivery 3 30.00 90.00"), (670, "Packing 2 45.00")])
    )
    for check in report.row_checks:
        assert check.status == "unavailable"
        assert check.anchor_source_status == "needs_review"
        assert check.field_source_status == "verified"
        result = next(f for f in report.fields if f.path == check.field)
        assert result.status == "needs_review"


class ReorderedItem(BaseModel):
    number: Evidenced[float]
    description: Evidenced[str]


class Form(BaseModel):
    items: list[ReorderedItem]


def test_explicit_custom_rule_is_order_independent_and_can_be_disabled() -> None:
    data = Form(
        items=[
            ReorderedItem(
                number=Evidenced(value=2, evidence=["2"]),
                description=Evidenced(value="Delivery", evidence=["Delivery"]),
            )
        ]
    )
    doc = document([(700, "Delivery 2 90.00"), (670, "Packing 2 15.00")])
    declared = verify(data, doc, row_rules=[RowEvidenceRule("items", "description", ("number",))])
    assert declared.fields[0].status == "verified"
    assert declared.row_checks[0].status == "same_line"
    assert declared.row_checks[0].anchor == "items[0].description"
    # A generic list does not imply a table-row constraint.
    assert verify(data, doc).row_checks == []
    wrong = document([(700, "Delivery 3 90.00"), (670, "Packing 2 15.00")])
    disabled = verify(invoice(), wrong, row_rules=[])
    assert disabled.row_checks == []
    assert next(f for f in disabled.fields if f.path.endswith(".quantity")).status == "verified"


def test_nested_collection_paths_are_explicit_and_validated() -> None:
    class Wrapper(BaseModel):
        payload: Form

    data = Wrapper(
        payload=Form(
            items=[
                ReorderedItem(
                    number=Evidenced(value=2, evidence=["2"]),
                    description=Evidenced(value="Delivery", evidence=["Delivery"]),
                )
            ]
        )
    )
    rule = RowEvidenceRule("payload.items", "description", ("number",))
    doc = document([(700, "Delivery 3"), (670, "Packing 2")])
    report = verify(data, doc, row_rules=[rule])
    assert report.row_checks[0].field == "payload.items[0].number"
    assert report.row_checks[0].status == "separate"
    for rules in (
        [RowEvidenceRule("payload.typo", "description", ("number",))],
        [RowEvidenceRule("payload.items", "missing", ("number",))],
        [rule, rule],
    ):
        with pytest.raises(ValueError, match="row rule"):
            verify(data, doc, row_rules=rules)


def test_arithmetic_does_not_rewrite_the_recorded_source_or_row_evidence() -> None:
    row = item()
    row.unit_price = Evidenced(value=40, evidence=["40.00"])
    report = verify(invoice(row), document([(700, "Delivery 2 40.00 90.00")]))
    assert report.cross_field_checks[0].status == "failed"
    assert all(check.status == "same_line" for check in report.row_checks)
    assert all(check.field_source_status == "verified" for check in report.row_checks)
    assert all(
        next(f for f in report.fields if f.path == check.field).status == "needs_review"
        for check in report.row_checks
    )
