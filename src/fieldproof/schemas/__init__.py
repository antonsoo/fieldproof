from pydantic import BaseModel

from fieldproof.schemas.base import Evidenced, iter_evidenced_fields
from fieldproof.schemas.contract import ContractKeyTerms
from fieldproof.schemas.invoice import Invoice, LineItem
from fieldproof.schemas.receipt import Receipt, ReceiptItem

#: Name -> schema, used by the CLI's `--schema` flag and the server's upload form.
BUILTIN_SCHEMAS: dict[str, type[BaseModel]] = {
    "invoice": Invoice,
    "receipt": Receipt,
    "contract": ContractKeyTerms,
}


def resolve_schema(name: str) -> type[BaseModel] | None:
    """Look up a built-in schema by its registry key ("invoice") or its
    Python class name ("Invoice"), case-insensitively.

    `fieldproof extract` writes the registry key into `result.json`'s
    "schema" field, but `Extractor.extract()` (used directly by library
    callers, or by another tool producing its own result JSON per the
    "bring your own extractor" contract) has no registry to consult and
    naturally reaches for the class name instead - `fieldproof verify`
    needs to accept either.
    """
    key = name.lower()
    if key in BUILTIN_SCHEMAS:
        return BUILTIN_SCHEMAS[key]
    for schema in BUILTIN_SCHEMAS.values():
        if schema.__name__.lower() == key:
            return schema
    return None


__all__ = [
    "BUILTIN_SCHEMAS",
    "ContractKeyTerms",
    "Evidenced",
    "Invoice",
    "LineItem",
    "Receipt",
    "ReceiptItem",
    "iter_evidenced_fields",
    "resolve_schema",
]
