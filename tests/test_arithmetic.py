from __future__ import annotations

import json
from decimal import Inexact, localcontext
from fractions import Fraction

import pytest

from fieldproof.schemas import Evidenced
from fieldproof.schemas.invoice import Invoice, LineItem
from fieldproof.schemas.receipt import Receipt, ReceiptItem
from fieldproof.verify.cross_field import audit_invoice, audit_receipt, check_invoice
from fieldproof.verify.engine import FieldStatus, verify


def evidenced(value):
    return Evidenced(value=value, evidence=[str(value)], page=1)


def invoice(**updates) -> Invoice:
    return Invoice(
        vendor_name=evidenced("Example Workshop"),
        invoice_number=evidenced("FP-MATH"),
        issue_date=evidenced("2026-10-09"),
        **{"total": evidenced(43.09), **updates},
    )


def item(quantity=3.0, price=19.95, amount=39.9) -> LineItem:
    return LineItem(
        description=evidenced("Precision bolts"),
        quantity=evidenced(quantity) if quantity is not None else None,
        unit_price=evidenced(price) if price is not None else None,
        amount=evidenced(amount),
    )


def test_individually_supported_pdf_values_still_require_consistent_line_arithmetic() -> None:
    from io import BytesIO

    from reportlab.pdfgen.canvas import Canvas

    from fieldproof.document.loader import load_pdf

    data = invoice(line_items=[item()], subtotal=evidenced(39.9), tax=evidenced(3.19))
    # Separate labelled lines make every value's citation independently unambiguous.
    from fieldproof.schemas import iter_evidenced_fields

    stream = BytesIO()
    canvas = Canvas(stream)
    for index, (path, value) in enumerate(iter_evidenced_fields(data)):
        text = f"{path}: {value.value}"
        value.evidence = [text]
        canvas.drawString(36, 750 - index * 24, text)
    canvas.save()
    report = verify(data, load_pdf(stream.getvalue()))
    flagged = {field.path for field in report.fields if field.status == FieldStatus.NEEDS_REVIEW}
    assert flagged == {"line_items[0].quantity", "line_items[0].unit_price", "line_items[0].amount"}
    check = report.cross_field_checks[0]
    assert (check.computed, check.observed, check.difference) == ("59.85", "39.9", "-19.95")
    assert "before discounts or adjustments" in check.message
    assert report.counts == {"verified": 7, "needs_review": 3, "unsupported": 0}
    assert report.to_dict()["cross_field_checks"][0]["computed"] == "59.85"


@pytest.mark.parametrize("quantity,price", [(None, 19.95), (3.0, None)])
def test_missing_line_inputs_are_recorded_without_inventing_zero(quantity, price) -> None:
    check = audit_invoice(invoice(line_items=[item(quantity, price)]))[0]
    assert check.status == "not_checked"
    assert None in check.operands.values()
    assert check.computed is None and check.observed is None and check.difference is None
    assert check.issue() is None


def test_zero_negative_and_fractional_quantities_have_real_calculations() -> None:
    for quantity, price, amount in [(0, 19.95, 0), (-2, 19.95, -39.9), (0.25, 19.96, 4.99)]:
        check = audit_invoice(invoice(line_items=[item(quantity, price, amount)]))[0]
        assert check.status == "passed"
        assert check.difference == "0"


@pytest.mark.parametrize(
    "observed,expected", [(1.02, "passed"), (0.98, "passed"), (1.02001, "failed")]
)
def test_the_two_cent_boundary_is_inclusive(observed, expected) -> None:
    data = invoice(
        line_items=[item(None, None, 0.2), item(None, None, 0.8)],
        subtotal=evidenced(observed),
    )
    check = next(c for c in audit_invoice(data) if c.rule == "invoice.items_subtotal")
    assert check.status == expected
    assert Fraction(check.difference) == Fraction(str(observed)) - 1


def test_a_small_tax_is_not_erased_by_a_large_subtotal() -> None:
    data = invoice(subtotal=evidenced(1e16), tax=evidenced(1.0), total=evidenced(1e16))
    check = next(c for c in audit_invoice(data) if c.rule == "invoice.subtotal_tax_total")
    assert check.status == "failed"
    assert check.computed == "10000000000000001"
    assert check.difference == "-1"
    assert check.fields == ("subtotal", "tax", "total")


def test_decimal_context_and_float_overflow_cannot_change_an_exact_result() -> None:
    data = invoice(
        line_items=[item(None, None, 1e308), item(None, None, 1), item(None, None, -1e308)],
        subtotal=evidenced(0),
    )
    with localcontext() as context:
        context.prec = 2
        context.Emax = 9
        context.traps[Inexact] = True
        checks = audit_invoice(data)
        huge = audit_invoice(invoice(line_items=[item(1e308, 1e308, 1e308)]))[0]
    subtotal = next(c for c in checks if c.rule == "invoice.items_subtotal")
    assert subtotal.computed == "1" and subtotal.status == "failed"
    assert Fraction(huge.computed) == Fraction("1e616")
    assert Fraction(huge.difference) == Fraction("1e308") - Fraction("1e616")
    assert huge.status == "failed"


def test_unavailable_arithmetic_is_distinct_from_a_passing_check() -> None:
    checks = audit_invoice(invoice())
    assert all(c.status == "not_checked" for c in checks)
    assert "no item amounts" in checks[0].message
    assert checks[1].operands == {"subtotal": None, "tax": None, "total": "43.09"}
    for value in [float("nan"), float("inf"), -float("inf")]:
        check = audit_invoice(invoice(line_items=[item(value)]))[0]
        assert check.status == "not_checked" and check.computed is None
        json.dumps(check.to_dict(), allow_nan=False)


@pytest.mark.parametrize("tolerance", [-0.01, float("nan"), float("inf")])
def test_invalid_tolerances_are_refused(tolerance) -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        check_invoice(invoice(), tolerance=tolerance)


def test_receipt_rules_keep_missing_tax_separate_from_zero_tax() -> None:
    data = Receipt(
        merchant_name=evidenced("Shop"),
        transaction_date=evidenced("2026-10-09"),
        items=[ReceiptItem(description=evidenced("Item"), amount=evidenced(1.0))],
        subtotal=evidenced(1.02),
        total=evidenced(1.02),
    )
    checks = audit_receipt(data)
    assert [c.status for c in checks] == ["passed", "not_checked"]
    data.tax = evidenced(0.0)
    assert audit_receipt(data)[1].status == "passed"


def test_date_checks_keep_the_existing_claimed_date_interpretation() -> None:
    for due, status in [(None, "not_checked"), ("2026-10-08", "failed"), ("2026-10-09", "passed")]:
        checks = audit_invoice(invoice(due_date=evidenced(due) if due else None))
        assert checks[-1].rule == "invoice.due_date_order"
        assert checks[-1].status == status
