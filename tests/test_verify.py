from __future__ import annotations

from pathlib import Path

from fieldproof.document.loader import load_pdf
from fieldproof.schemas import Evidenced, Invoice, LineItem
from fieldproof.verify.cross_field import check_invoice
from fieldproof.verify.engine import FieldStatus, verify
from fieldproof.verify.value_checks import (
    check_bool,
    check_date,
    check_number,
    check_string,
    parse_all_numbers,
    parse_date,
    parse_number,
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


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


def test_check_number_matches_any_number_in_a_whole_row_quote() -> None:
    # Row-level evidence often quotes the whole line ("Fuel surcharge 1
    # 210.50 210.50") rather than just the one value being checked - the
    # claimed value has to be found *somewhere* in it, not just as the
    # last number.
    row = "Fuel surcharge 1 210.50 210.50"
    assert check_number(1.0, row).supported  # quantity
    assert check_number(210.5, row).supported  # unit_price and amount
    assert not check_number(999.0, row).supported


def test_parse_all_numbers_excludes_percentages() -> None:
    assert parse_all_numbers("Tax (8.5%) $208.93") == [208.93]
    assert parse_all_numbers("Fuel surcharge 1 210.50 210.50") == [1.0, 210.50, 210.50]


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


# --- ambiguous-quote disambiguation (regression: "1" inside "4821") ---


def _invoice_with_bare_row_quotes() -> Invoice:
    """An Invoice grounded against examples/invoice.pdf using deliberately
    terse, ambiguous evidence for the row-level numeric fields (just "1",
    not "Fuel surcharge 1 210.50 210.50") - the shape a less careful
    extraction would produce. Regression coverage for the bug where a bare
    "1" grounded to the trailing digit of the "4821" street address instead
    of either line item's quantity."""
    return Invoice(
        vendor_name=Evidenced(
            value="Northwind Freight & Supply Co.",
            evidence=["Northwind Freight & Supply Co."],
            page=1,
        ),
        invoice_number=Evidenced(
            value="NW-20260214", evidence=["Invoice Number: NW-20260214"], page=1
        ),
        issue_date=Evidenced(
            value="2026-02-14", evidence=["Issue Date: February 14, 2026"], page=1
        ),
        total=Evidenced(value=2666.93, evidence=["Total Due $2,666.93"], page=1),
        line_items=[
            LineItem(
                description=Evidenced(value="Fuel surcharge", evidence=["Fuel surcharge"], page=1),
                quantity=Evidenced(value=1, evidence=["1"], page=1),
                amount=Evidenced(value=210.5, evidence=["Fuel surcharge 1 210.50 210.50"], page=1),
            ),
            LineItem(
                description=Evidenced(
                    value="Warehouse handling fee", evidence=["Warehouse handling fee"], page=1
                ),
                quantity=Evidenced(value=1, evidence=["1"], page=1),
                amount=Evidenced(
                    value=312.5, evidence=["Warehouse handling fee 1 312.50 312.50"], page=1
                ),
            ),
        ],
    )


def test_verify_never_grounds_a_bare_quote_inside_a_longer_number() -> None:
    doc = load_pdf(EXAMPLES_DIR / "invoice.pdf")
    report = verify(_invoice_with_bare_row_quotes(), doc)
    quantities = [f for f in report.fields if f.path.endswith(".quantity")]
    assert len(quantities) == 2
    for q in quantities:
        assert q.matched_text == "1"


def test_verify_disambiguates_ambiguous_row_quote_by_locality() -> None:
    """Each line item's bare "1" quantity must ground to *its own* row (the
    one its description was grounded to), not the other line item's row,
    even though "1" appears as a standalone word twice on the page."""
    doc = load_pdf(EXAMPLES_DIR / "invoice.pdf")
    report = verify(_invoice_with_bare_row_quotes(), doc)
    by_path = {f.path: f for f in report.fields}

    description_0_top = by_path["line_items[0].description"].rects[0]["top"]
    quantity_0_top = by_path["line_items[0].quantity"].rects[0]["top"]
    description_1_top = by_path["line_items[1].description"].rects[0]["top"]
    quantity_1_top = by_path["line_items[1].quantity"].rects[0]["top"]

    assert quantity_0_top == description_0_top
    assert quantity_1_top == description_1_top
    assert description_0_top != description_1_top

    assert by_path["line_items[0].quantity"].status == FieldStatus.VERIFIED
    assert by_path["line_items[1].quantity"].status == FieldStatus.VERIFIED


def test_verify_marks_ambiguous_quote_needs_review_when_no_locality_hint() -> None:
    """A top-level (non-row) field has no sibling to anchor against, so if
    its quote is genuinely ambiguous, the field must not silently pick one
    occurrence - it has to say so."""
    doc = load_pdf(EXAMPLES_DIR / "invoice.pdf")
    invoice = Invoice(
        vendor_name=Evidenced(
            value="Northwind Freight & Supply Co.",
            evidence=["Northwind Freight & Supply Co."],
            page=1,
        ),
        invoice_number=Evidenced(
            value="NW-20260214", evidence=["Invoice Number: NW-20260214"], page=1
        ),
        issue_date=Evidenced(
            value="2026-02-14", evidence=["Issue Date: February 14, 2026"], page=1
        ),
        total=Evidenced(value=2666.93, evidence=["Total Due $2,666.93"], page=1),
        # "1" appears as a standalone word twice on this page (two line
        # items' quantities); po_number is a top-level field with no row
        # siblings to disambiguate against.
        po_number=Evidenced(value="1", evidence=["1"], page=1),
        line_items=[],
    )
    report = verify(invoice, doc)
    po_result = next(f for f in report.fields if f.path == "po_number")
    assert po_result.status == FieldStatus.NEEDS_REVIEW
    assert any("ambiguous" in r for r in po_result.reasons)
