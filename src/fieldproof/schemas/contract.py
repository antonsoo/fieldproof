"""The built-in contract key-terms extraction template.

Contracts don't have the arithmetic structure invoices and receipts do, so
there are no cross-field checks for this schema in `fieldproof.verify` -
every field still goes through evidence grounding and value-vs-evidence
consistency, just no line-item sums or date-ordering rules.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from fieldproof.schemas.base import Evidenced


class ContractKeyTerms(BaseModel):
    """Key terms of a contract: parties, dates, and obligations."""

    party_a: Evidenced[str]
    party_b: Evidenced[str]
    effective_date: Evidenced[str] = Field(description="ISO-8601 date")
    term_length: Evidenced[str] | None = Field(
        default=None, description="e.g. '12 months', 'until terminated'"
    )
    termination_notice_period: Evidenced[str] | None = None
    governing_law: Evidenced[str] | None = None
    total_contract_value: Evidenced[float] | None = None
    key_obligations: list[Evidenced[str]] = Field(default_factory=list)
