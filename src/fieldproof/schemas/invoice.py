"""The built-in invoice extraction template.

Dates and money are kept as `str`/`float` (not `date`/`Decimal`) so the
schema serializes to plain JSON Schema for the provider's structured-output
call - `fieldproof.verify.value_checks` is responsible for parsing
`issue_date`/`due_date` as ISO-8601 and comparing amounts with a tolerance,
not this module.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from fieldproof.schemas.base import Evidenced


class LineItem(BaseModel):
    description: Evidenced[str]
    quantity: Evidenced[float] | None = None
    unit_price: Evidenced[float] | None = None
    amount: Evidenced[float]


class Invoice(BaseModel):
    """Vendor invoice: line items, totals, and payment terms."""

    vendor_name: Evidenced[str]
    invoice_number: Evidenced[str]
    issue_date: Evidenced[str] = Field(description="ISO-8601 date, e.g. 2026-03-14")
    due_date: Evidenced[str] | None = Field(default=None, description="ISO-8601 date")
    currency: Evidenced[str] | None = Field(default=None, description="ISO-4217 code, e.g. USD")
    po_number: Evidenced[str] | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Evidenced[float] | None = None
    tax: Evidenced[float] | None = None
    total: Evidenced[float]
    payment_terms: Evidenced[str] | None = None
