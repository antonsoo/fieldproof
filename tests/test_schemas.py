from __future__ import annotations

from fieldproof.schemas import BUILTIN_SCHEMAS, ContractKeyTerms, Evidenced, Invoice, Receipt
from fieldproof.schemas.base import iter_evidenced_fields


def test_builtin_schemas_registry() -> None:
    assert set(BUILTIN_SCHEMAS) == {"invoice", "receipt", "contract"}
    assert BUILTIN_SCHEMAS["invoice"] is Invoice
    assert BUILTIN_SCHEMAS["receipt"] is Receipt
    assert BUILTIN_SCHEMAS["contract"] is ContractKeyTerms


def test_iter_evidenced_fields_walks_nested_lists() -> None:
    from fieldproof.schemas.invoice import LineItem

    invoice = Invoice(
        vendor_name=Evidenced(value="Acme", evidence=["Acme"]),
        invoice_number=Evidenced(value="1", evidence=["1"]),
        issue_date=Evidenced(value="2026-01-01", evidence=["2026-01-01"]),
        total=Evidenced(value=10.0, evidence=["10"]),
        line_items=[
            LineItem(
                description=Evidenced(value="A", evidence=["A"]),
                amount=Evidenced(value=5.0, evidence=["5"]),
            ),
            LineItem(
                description=Evidenced(value="B", evidence=["B"]),
                amount=Evidenced(value=5.0, evidence=["5"]),
            ),
        ],
    )
    paths = {path for path, _ in iter_evidenced_fields(invoice)}
    assert "line_items[0].description" in paths
    assert "line_items[1].amount" in paths
    assert "vendor_name" in paths
    assert "total" in paths


def test_iter_evidenced_fields_works_on_custom_schema() -> None:
    """A user-defined schema (not one of the built-ins) still walks
    correctly - this is the contract for "bring your own Pydantic model"."""
    from pydantic import BaseModel

    class MyCustomForm(BaseModel):
        applicant_name: Evidenced[str]
        approved: Evidenced[bool]

    form = MyCustomForm(
        applicant_name=Evidenced(value="Jane Doe", evidence=["Jane Doe"]),
        approved=Evidenced(value=True, evidence=["Approved"]),
    )
    paths = dict(iter_evidenced_fields(form))
    assert set(paths) == {"applicant_name", "approved"}
    assert paths["applicant_name"].value == "Jane Doe"
