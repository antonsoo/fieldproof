"""The built-in point-of-sale receipt extraction template."""

from __future__ import annotations

from pydantic import BaseModel, Field

from fieldproof.schemas.base import Evidenced


class ReceiptItem(BaseModel):
    description: Evidenced[str]
    quantity: Evidenced[float] | None = None
    amount: Evidenced[float]


class Receipt(BaseModel):
    """Point-of-sale receipt: merchant, items, tender."""

    merchant_name: Evidenced[str]
    transaction_date: Evidenced[str] = Field(description="ISO-8601 date, e.g. 2026-03-14")
    items: list[ReceiptItem] = Field(default_factory=list)
    subtotal: Evidenced[float] | None = None
    tax: Evidenced[float] | None = None
    total: Evidenced[float]
    payment_method: Evidenced[str] | None = None
