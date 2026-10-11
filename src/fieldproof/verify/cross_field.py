"""Inspectable consistency checks on the built-in schemas' extracted claims.

Arithmetic agreement does not establish grounding, completeness of the document,
or business correctness. In particular, line extensions are before unmodelled
discounts/adjustments. Disagreement sends the participating fields to review.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Context, Decimal, localcontext
from typing import Any, Literal

from pydantic import BaseModel

from fieldproof.schemas.invoice import Invoice
from fieldproof.schemas.receipt import Receipt
from fieldproof.verify.value_checks import parse_iso_date

# Absolute, inclusive tolerance in the extracted amounts' units. This is not a
# currency-specific rounding rule and does not round each line before summing.
SUM_TOLERANCE = 0.02


@dataclass(frozen=True, slots=True)
class CrossFieldIssue:
    fields: tuple[str, ...]
    message: str


@dataclass(frozen=True, slots=True)
class CrossFieldCheck:
    rule: str
    fields: tuple[str, ...]
    status: Literal["passed", "failed", "not_checked"]
    message: str
    # Numeric operands/results are decimal strings, never rounded JSON floats.
    # None means the field was absent, not a zero silently supplied by the checker.
    operands: dict[str, str | None] = field(default_factory=dict)
    computed: str | None = None
    observed: str | None = None
    difference: str | None = None  # observed - computed
    tolerance: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "fields": list(self.fields)}

    def issue(self) -> CrossFieldIssue | None:
        return CrossFieldIssue(self.fields, self.message) if self.status == "failed" else None


def _text(value: Decimal) -> str:
    if value.is_zero():
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _tolerance(value: float) -> Decimal:
    tolerance = Decimal(str(value))
    if not tolerance.is_finite() or tolerance < 0:
        raise ValueError("cross-field tolerance must be finite and non-negative")
    return tolerance


def _sum_precision(values: list[Decimal]) -> int:
    # Keep every decimal place across the exponent span, plus possible carries.
    # A fresh Context also isolates checks from a caller's decimal precision/traps.
    return max(
        28,
        max(value.adjusted() for value in values)
        - min(int(value.as_tuple().exponent) for value in values)
        + len(str(len(values)))
        + 2,
    )


def _calculation(
    rule: str,
    inputs: dict[str, float | None],
    output_path: str,
    output_value: float | None,
    tolerance: Decimal,
    *,
    operation: Literal["sum", "product"] = "sum",
    label: str,
    output_label: str,
) -> CrossFieldCheck:
    fields = (*inputs, output_path)
    raw = {**inputs, output_path: output_value}
    operands = {path: None if value is None else str(value) for path, value in raw.items()}
    missing = [path for path, value in raw.items() if value is None]
    values = {path: Decimal(str(value)) for path, value in raw.items() if value is not None}
    nonfinite = [path for path, value in values.items() if not value.is_finite()]
    if not inputs or missing or nonfinite:
        reason = (
            "no item amounts were extracted"
            if not inputs
            else "missing " + ", ".join(missing)
            if missing
            else "non-finite " + ", ".join(nonfinite)
        )
        return CrossFieldCheck(
            rule,
            fields,
            "not_checked",
            f"{label} not checked: {reason}",
            operands,
            tolerance=_text(tolerance),
        )

    terms = [values[path] for path in inputs]
    if operation == "product":
        precision = max(28, sum(len(value.as_tuple().digits) for value in terms) + 2)
        with localcontext(Context(prec=precision)):
            computed = terms[0] * terms[1]
    else:
        with localcontext(Context(prec=_sum_precision(terms))):
            computed = sum(terms, Decimal(0))
    observed = values[output_path]
    with localcontext(Context(prec=_sum_precision([observed, computed, tolerance]))):
        difference = observed - computed
        agrees = abs(difference) <= tolerance
    qualifier = " (before discounts or adjustments)" if operation == "product" else ""
    verb = "matches" if agrees else "but"
    return CrossFieldCheck(
        rule,
        fields,
        "passed" if agrees else "failed",
        f"{label} = {_text(computed)}{qualifier} {verb} {output_label} {_text(observed)} "
        f"(difference {_text(difference)}; tolerance {_text(tolerance)})",
        operands,
        computed=_text(computed),
        observed=_text(observed),
        difference=_text(difference),
        tolerance=_text(tolerance),
    )


def _date_check(invoice: Invoice) -> CrossFieldCheck:
    fields = ("issue_date", "due_date")
    due_value = invoice.due_date.value if invoice.due_date is not None else None
    operands = {"issue_date": invoice.issue_date.value, "due_date": due_value}
    issue = parse_iso_date(invoice.issue_date.value)
    due = parse_iso_date(due_value) if due_value is not None else None
    if issue is None or due is None:
        return CrossFieldCheck(
            "invoice.due_date_order",
            fields,
            "not_checked",
            "date order not checked: both extracted dates must be calendar-valid YYYY-MM-DD values",
            operands,
        )
    before = due < issue
    return CrossFieldCheck(
        "invoice.due_date_order",
        fields,
        "failed" if before else "passed",
        f"due date {due.isoformat()} is {'before' if before else 'on or after'} "
        f"issue date {issue.isoformat()}",
        operands,
    )


def audit_invoice(invoice: Invoice, *, tolerance: float = SUM_TOLERANCE) -> list[CrossFieldCheck]:
    amount_tolerance = _tolerance(tolerance)
    checks = []
    for index, item in enumerate(invoice.line_items):
        row = f"line_items[{index}]"
        checks.append(
            _calculation(
                "invoice.line_extension",
                {
                    f"{row}.quantity": item.quantity.value if item.quantity is not None else None,
                    f"{row}.unit_price": item.unit_price.value
                    if item.unit_price is not None
                    else None,
                },
                f"{row}.amount",
                item.amount.value,
                amount_tolerance,
                operation="product",
                label=f"{row}: quantity x unit price",
                output_label="amount",
            )
        )
    checks.append(
        _calculation(
            "invoice.items_subtotal",
            {
                f"line_items[{i}].amount": item.amount.value
                for i, item in enumerate(invoice.line_items)
            },
            "subtotal",
            invoice.subtotal.value if invoice.subtotal is not None else None,
            amount_tolerance,
            label="line items sum",
            output_label="subtotal",
        )
    )
    checks.append(
        _calculation(
            "invoice.subtotal_tax_total",
            {
                "subtotal": invoice.subtotal.value if invoice.subtotal is not None else None,
                "tax": invoice.tax.value if invoice.tax is not None else None,
            },
            "total",
            invoice.total.value,
            amount_tolerance,
            label="subtotal + tax",
            output_label="total",
        )
    )
    checks.append(_date_check(invoice))
    return checks


def audit_receipt(receipt: Receipt, *, tolerance: float = SUM_TOLERANCE) -> list[CrossFieldCheck]:
    amount_tolerance = _tolerance(tolerance)
    return [
        _calculation(
            "receipt.items_subtotal",
            {f"items[{i}].amount": item.amount.value for i, item in enumerate(receipt.items)},
            "subtotal",
            receipt.subtotal.value if receipt.subtotal is not None else None,
            amount_tolerance,
            label="items sum",
            output_label="subtotal",
        ),
        _calculation(
            "receipt.subtotal_tax_total",
            {
                "subtotal": receipt.subtotal.value if receipt.subtotal is not None else None,
                "tax": receipt.tax.value if receipt.tax is not None else None,
            },
            "total",
            receipt.total.value,
            amount_tolerance,
            label="subtotal + tax",
            output_label="total",
        ),
    ]


def audit_cross_field(data: BaseModel) -> list[CrossFieldCheck]:
    """All attempted built-in checks, including missing operands. Custom schemas have no rules."""
    if isinstance(data, Invoice):
        return audit_invoice(data)
    if isinstance(data, Receipt):
        return audit_receipt(data)
    return []


def check_invoice(invoice: Invoice, *, tolerance: float = SUM_TOLERANCE) -> list[CrossFieldIssue]:
    return [
        issue for check in audit_invoice(invoice, tolerance=tolerance) if (issue := check.issue())
    ]


def check_receipt(receipt: Receipt, *, tolerance: float = SUM_TOLERANCE) -> list[CrossFieldIssue]:
    return [
        issue for check in audit_receipt(receipt, tolerance=tolerance) if (issue := check.issue())
    ]


def check_cross_field(data: BaseModel) -> list[CrossFieldIssue]:
    """Compatibility interface returning only failed checks."""
    return [issue for check in audit_cross_field(data) if (issue := check.issue())]
