from __future__ import annotations

from fieldproof.document.loader import load_pdf
from fieldproof.schemas import Evidenced, Invoice, LineItem
from fieldproof.verify.cross_field import check_invoice
from fieldproof.verify.engine import FieldStatus, verify
from fieldproof.verify.value_checks import (
    check_bool,
    check_date,
    check_number,
    check_string,
    parse_date,
    parse_number,
)


def test_parse_number_handles_currency_and_thousands() -> None:
    assert parse_number("$1,234.50") == 1234.50
    assert parse_number("(50.00)") == -50.0
    assert parse_number("not a number") is None


def test_parse_date_handles_common_formats() -> None:
    from datetime import date

    assert parse_date("2026-03-14") == date(2026, 3, 14)
    assert parse_date("March 14, 2026") == date(2026, 3, 14)
    assert parse_date("03/14/2026") == date(2026, 3, 14)
    assert parse_date("gibberish") is None


def test_check_number_within_tolerance() -> None:
    assert check_number(110.0, "$110.00").supported
    assert not check_number(110.0, "$999.00").supported


def test_check_date_agrees_across_formats() -> None:
    assert check_date("2026-01-01", "January 1, 2026").supported
    assert not check_date("2026-01-01", "February 2, 2026").supported


def test_check_string_fuzzy_tolerant_of_minor_differences() -> None:
    assert check_string("Acme Corporation", "Acme Corporation").supported
    assert not check_string("Acme Corporation", "a totally different vendor name").supported


def test_check_bool_reads_yes_no_language() -> None:
    assert check_bool(True, "Confirmed: yes").supported
    assert check_bool(False, "Status: denied").supported


def _invoice(**overrides: object) -> Invoice:
    base = dict(
        vendor_name=Evidenced(value="Acme Corporation", evidence=["Acme Corporation"], page=1),
        invoice_number=Evidenced(value="INV-1001", evidence=["Invoice Number: INV-1001"], page=1),
        issue_date=Evidenced(value="2026-01-01", evidence=["Issue Date: January 1, 2026"], page=1),
        due_date=Evidenced(value="2026-01-31", evidence=["Due Date: January 31, 2026"], page=1),
        total=Evidenced(value=110.0, evidence=["Total: $110.00"], page=1),
        subtotal=Evidenced(value=100.0, evidence=["Subtotal: $100.00"], page=1),
        tax=Evidenced(value=10.0, evidence=["Tax: $10.00"], page=1),
        line_items=[
            LineItem(
                description=Evidenced(value="Widget Assembly", evidence=["Widget Assembly"]),
                amount=Evidenced(value=100.0, evidence=["$50.00"]),
            )
        ],
    )
    base.update(overrides)
    return Invoice(**base)


def test_verify_all_fields_verified_when_grounded_and_consistent(
    simple_invoice_pdf_bytes: bytes,
) -> None:
    doc = load_pdf(simple_invoice_pdf_bytes)
    invoice = _invoice(
        line_items=[
            LineItem(
                description=Evidenced(value="Widget Assembly", evidence=["Widget Assembly"]),
                amount=Evidenced(value=100.0, evidence=["Subtotal: $100.00"]),
            )
        ]
    )
    report = verify(invoice, doc)
    statuses = {f.path: f.status for f in report.fields}
    assert statuses["vendor_name"] == FieldStatus.VERIFIED
    assert statuses["total"] == FieldStatus.VERIFIED
    assert report.counts["unsupported"] == 0


def test_verify_flags_hallucinated_field_as_unsupported(simple_invoice_pdf_bytes: bytes) -> None:
    doc = load_pdf(simple_invoice_pdf_bytes)
    invoice = _invoice(
        po_number=Evidenced(
            value="PO-9999", evidence=["a quote that is nowhere on the page"], page=1
        )
    )
    report = verify(invoice, doc)
    po_result = next(f for f in report.fields if f.path == "po_number")
    assert po_result.status == FieldStatus.UNSUPPORTED


def test_verify_flags_field_with_no_evidence_as_unsupported(
    simple_invoice_pdf_bytes: bytes,
) -> None:
    doc = load_pdf(simple_invoice_pdf_bytes)
    invoice = _invoice(po_number=Evidenced(value="PO-9999", evidence=[], page=1))
    report = verify(invoice, doc)
    po_result = next(f for f in report.fields if f.path == "po_number")
    assert po_result.status == FieldStatus.UNSUPPORTED
    assert "no evidence" in po_result.reasons[0]


def test_verify_flags_value_evidence_mismatch_as_needs_review(
    simple_invoice_pdf_bytes: bytes,
) -> None:
    doc = load_pdf(simple_invoice_pdf_bytes)
    invoice = _invoice(total=Evidenced(value=999.0, evidence=["Total: $110.00"], page=1))
    report = verify(invoice, doc)
    total_result = next(f for f in report.fields if f.path == "total")
    assert total_result.status == FieldStatus.NEEDS_REVIEW
    assert any("999" in r for r in total_result.reasons)


def test_cross_field_line_items_must_sum_to_subtotal() -> None:
    invoice = _invoice(
        subtotal=Evidenced(value=100.0, evidence=["Subtotal: $100.00"]),
        line_items=[
            LineItem(
                description=Evidenced(value="Widget", evidence=["Widget"]),
                amount=Evidenced(value=40.0, evidence=["$40"]),
            )
        ],
    )
    issues = check_invoice(invoice)
    assert any("line items sum" in i.message for i in issues)


def test_cross_field_due_date_before_issue_date_flagged() -> None:
    invoice = _invoice(
        issue_date=Evidenced(value="2026-02-01", evidence=["Feb 1, 2026"]),
        due_date=Evidenced(value="2026-01-01", evidence=["Jan 1, 2026"]),
    )
    issues = check_invoice(invoice)
    assert any("before issue date" in i.message for i in issues)


def test_cross_field_issue_marks_participating_fields_needs_review(
    simple_invoice_pdf_bytes: bytes,
) -> None:
    doc = load_pdf(simple_invoice_pdf_bytes)
    invoice = _invoice(
        subtotal=Evidenced(value=100.0, evidence=["Subtotal: $100.00"]),
        tax=Evidenced(value=10.0, evidence=["Tax: $10.00"]),
        total=Evidenced(value=999.0, evidence=["Total: $110.00"]),
    )
    report = verify(invoice, doc)
    statuses = {f.path: f.status for f in report.fields}
    assert statuses["subtotal"] == FieldStatus.NEEDS_REVIEW
    assert statuses["tax"] == FieldStatus.NEEDS_REVIEW
    assert len(report.cross_field_issues) >= 1
