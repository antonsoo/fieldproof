"""Cross-field consistency rules for the built-in Invoice/Receipt schemas.

These are schema-specific by nature - "line items sum to the subtotal" only
means something for a schema that has line items - so unlike
`fieldproof.verify.value_checks` (which works on any `Evidenced[str|float|bool]`
leaf via `iter_evidenced_fields`), this module dispatches on the concrete
schema type. A custom Pydantic model gets value-vs-evidence checks and
grounding, but no cross-field rules, unless you extend this dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from fieldproof.schemas.invoice import Invoice
from fieldproof.schemas.receipt import Receipt
from fieldproof.verify.value_checks import parse_date

#: Absolute tolerance, in currency units, for "do these amounts add up".
#: Covers per-line-item rounding that a strict sum would flag spuriously.
SUM_TOLERANCE = 0.02


@dataclass(frozen=True, slots=True)
class CrossFieldIssue:
    fields: tuple[str, ...]
    message: str


def check_invoice(invoice: Invoice, *, tolerance: float = SUM_TOLERANCE) -> list[CrossFieldIssue]:
    issues: list[CrossFieldIssue] = []

    if invoice.line_items and invoice.subtotal is not None:
        computed = sum(item.amount.value for item in invoice.line_items)
        if abs(computed - invoice.subtotal.value) > tolerance:
            issues.append(
                CrossFieldIssue(
                    fields=(
                        "subtotal",
                        *(f"line_items[{i}].amount" for i in range(len(invoice.line_items))),
                    ),
                    message=(
                        f"line items sum to {computed:.2f} but subtotal is "
                        f"{invoice.subtotal.value:.2f}"
                    ),
                )
            )

    if invoice.subtotal is not None and invoice.tax is not None:
        computed_total = invoice.subtotal.value + invoice.tax.value
        if abs(computed_total - invoice.total.value) > tolerance:
            issues.append(
                CrossFieldIssue(
                    fields=("subtotal", "tax", "total"),
                    message=(
                        f"subtotal + tax = {computed_total:.2f} but total is "
                        f"{invoice.total.value:.2f}"
                    ),
                )
            )

    if invoice.due_date is not None:
        issue_d = parse_date(invoice.issue_date.value)
        due_d = parse_date(invoice.due_date.value)
        if issue_d and due_d and due_d < issue_d:
            issues.append(
                CrossFieldIssue(
                    fields=("issue_date", "due_date"),
                    message=(
                        f"due date {due_d.isoformat()} is before issue date {issue_d.isoformat()}"
                    ),
                )
            )

    return issues


def check_receipt(receipt: Receipt, *, tolerance: float = SUM_TOLERANCE) -> list[CrossFieldIssue]:
    issues: list[CrossFieldIssue] = []

    if receipt.items and receipt.subtotal is not None:
        computed = sum(item.amount.value for item in receipt.items)
        if abs(computed - receipt.subtotal.value) > tolerance:
            issues.append(
                CrossFieldIssue(
                    fields=("subtotal", *(f"items[{i}].amount" for i in range(len(receipt.items)))),
                    message=(
                        f"items sum to {computed:.2f} but subtotal is {receipt.subtotal.value:.2f}"
                    ),
                )
            )

    if receipt.subtotal is not None and receipt.tax is not None:
        computed_total = receipt.subtotal.value + receipt.tax.value
        if abs(computed_total - receipt.total.value) > tolerance:
            issues.append(
                CrossFieldIssue(
                    fields=("subtotal", "tax", "total"),
                    message=(
                        f"subtotal + tax = {computed_total:.2f} but total is "
                        f"{receipt.total.value:.2f}"
                    ),
                )
            )

    return issues


def check_cross_field(data: BaseModel) -> list[CrossFieldIssue]:
    """Dispatch to the right cross-field checker for `data`'s type, or
    return no issues for a schema this module doesn't know about."""
    if isinstance(data, Invoice):
        return check_invoice(data)
    if isinstance(data, Receipt):
        return check_receipt(data)
    return []
