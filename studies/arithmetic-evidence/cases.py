"""Deliberately constructed arithmetic cases, not model output or real transactions."""

from copy import deepcopy


def evidence(value):
    return {"value": value, "evidence": [], "page": 1}


def row(quantity=3, price=19.95, amount=39.9, description="Precision bolts"):
    return {
        "description": evidence(description),
        "quantity": evidence(quantity) if quantity is not None else None,
        "unit_price": evidence(price) if price is not None else None,
        "amount": evidence(amount),
    }


def invoice(**changes):
    return {
        "vendor_name": evidence("Example Workshop"),
        "invoice_number": evidence("FP-MATH"),
        "issue_date": evidence("2026-10-09"),
        "line_items": [row()],
        "subtotal": evidence(39.9),
        "tax": evidence(3.19),
        "total": evidence(43.09),
        **changes,
    }


LINE = ["line_items[0].quantity", "line_items[0].unit_price", "line_items[0].amount"]
CASES = [
    {"id": "wrong-extension", "data": invoice(), "review": LINE},
    {"id": "correct-extension", "data": invoice(line_items=[row(2)]), "review": []},
    {
        "id": "unmodelled-discount",
        "data": invoice(),
        "review": LINE,
        "note": "Printed discount: 19.95. The extraction schema has no discount field.",
    },
    {"id": "missing-unit-price", "data": invoice(line_items=[row(price=None)]), "review": []},
    {
        "id": "inclusive-boundary",
        "data": invoice(
            line_items=[row(1, 1, 1)],
            subtotal=evidence(1.02),
            tax=evidence(0),
            total=evidence(1.02),
        ),
        "review": [],
    },
    {
        "id": "outside-boundary",
        "data": invoice(
            line_items=[row(1, 1, 1)],
            subtotal=evidence(1.021),
            tax=evidence(0),
            total=evidence(1.021),
        ),
        "review": ["line_items[0].amount", "subtotal"],
    },
    {
        "id": "tax-erased-by-float",
        "data": invoice(
            line_items=[], subtotal=evidence(1e16), tax=evidence(1), total=evidence(1e16)
        ),
        "review": ["subtotal", "tax", "total"],
    },
    {
        "id": "cancellation",
        "data": invoice(
            line_items=[
                row(None, None, 1e16, "Charge"),
                row(None, None, 1, "Fee"),
                row(None, None, -1e16, "Credit"),
            ],
            subtotal=evidence(0),
            tax=evidence(0),
            total=evidence(0),
        ),
        "review": [
            "line_items[0].amount",
            "line_items[1].amount",
            "line_items[2].amount",
            "subtotal",
        ],
    },
    {
        "id": "negative-quantity",
        "data": invoice(
            line_items=[row(-2, 19.95, -39.9)],
            subtotal=evidence(-39.9),
            tax=evidence(-3.19),
            total=evidence(-43.09),
        ),
        "review": [],
    },
    {
        "id": "fractional-quantity",
        "data": invoice(
            line_items=[row(0.25, 19.96, 4.99)],
            subtotal=evidence(4.99),
            tax=evidence(0),
            total=evidence(4.99),
        ),
        "review": [],
    },
    {
        "id": "rounded-line",
        "data": invoice(
            line_items=[row(3, 0.335, 1.01)],
            subtotal=evidence(1.01),
            tax=evidence(0),
            total=evidence(1.01),
        ),
        "review": [],
    },
    {
        "id": "unobserved-totals",
        "data": invoice(line_items=[], subtotal=None, tax=None),
        "review": [],
    },
    {
        "id": "receipt-boundary",
        "schema": "receipt",
        "data": {
            "merchant_name": evidence("Example Shop"),
            "transaction_date": evidence("2026-10-09"),
            "items": [
                {"description": evidence("Item A"), "amount": evidence(0.2)},
                {"description": evidence("Item B"), "amount": evidence(0.8)},
            ],
            "subtotal": evidence(1.02),
            "tax": evidence(0),
            "total": evidence(1.02),
        },
        "review": [],
    },
]


def cases():
    return deepcopy(CASES)
