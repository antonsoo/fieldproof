"""Constructed layouts, not a sample of extraction performance."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    name: str
    pages: list[list[tuple[float, float, str]]]
    description: str = "Delivery"
    quote: str = "Delivery"
    expected: str = "needs_review"
    text_edit_tolerance: int = 0
    # Coordinates belong to the known intended occurrence, not the implementation.
    expected_xy: tuple[float, float] | None = None


CASES = [
    Case("other_row", [[(50, 700, "Delivery 3"), (50, 600, "Packing 1"), (50, 500, "Handling 1")]]),
    Case(
        "adjacent_row", [[(50, 700, "Delivery 3"), (50, 686, "Packing 1"), (50, 672, "Handling 1")]]
    ),
    Case(
        "other_page", [[(50, 700, "Delivery 3")], [(50, 700, "Packing 1"), (50, 600, "Handling 1")]]
    ),
    Case(
        "unsupported_anchor",
        [[(50, 700, "Delivery 3"), (50, 600, "Packing 1"), (50, 500, "Handling 1")]],
        quote="Packing",
    ),
    Case("fuzzy_anchor", [[(50, 700, "Deliverx 1"), (50, 600, "Packing 1")]]),
    Case(
        "tolerated_anchor",
        [[(50, 700, "International deliverx 1"), (50, 600, "Packing 1")]],
        description="International delivery",
        quote="International delivery",
        text_edit_tolerance=1,
    ),
    Case("two_columns", [[(50, 700, "Delivery"), (250, 700, "1"), (350, 700, "1")]]),
    Case("two_columns_skew", [[(50, 700, "Delivery"), (250, 700, "1"), (350, 697, "1")]]),
    Case(
        "multiline_anchor",
        [[(50, 720, "Delivery"), (50, 680, "service"), (250, 700, "1"), (250, 600, "1")]],
        description="Delivery service",
        quote="Delivery service",
    ),
    Case(
        "one_same_row",
        [[(50, 700, "Delivery"), (250, 700, "1"), (50, 600, "Packing 1")]],
        expected="verified",
        expected_xy=(250, 700),
    ),
    Case(
        "one_same_row_skew",
        [[(50, 700, "Delivery"), (250, 697, "1"), (50, 600, "Packing 1")]],
        expected="verified",
        expected_xy=(250, 697),
    ),
    Case(
        "same_row_second",
        [[(50, 730, "Packing 1"), (50, 700, "Delivery"), (250, 700, "1")]],
        expected="verified",
        expected_xy=(250, 700),
    ),
    Case(
        "same_row_other_page_decoy",
        [[(50, 700, "Delivery"), (250, 700, "1")], [(250, 700, "1")]],
        expected="verified",
        expected_xy=(250, 700),
    ),
    Case(
        "case_only_anchor",
        [[(50, 700, "DELIVERY"), (250, 700, "1"), (50, 600, "Packing 1")]],
        expected="verified",
        expected_xy=(250, 700),
    ),
]
