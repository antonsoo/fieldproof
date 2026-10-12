"""Explicit, inspectable spatial checks for fields declared to form one table row.

Sharing a visual line is a necessary check for these rules, not proof of an
item's identity, a table column, or a field's semantic meaning. Wrapped rows
can require review even when all their claims are correct.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from fieldproof.ground.align import GroundingMatch, rects_for_match, unique_row_candidate
from fieldproof.schemas.base import Evidenced
from fieldproof.schemas.invoice import Invoice
from fieldproof.schemas.receipt import Receipt

if TYPE_CHECKING:
    from fieldproof.verify.engine import FieldVerification

_NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


@dataclass(frozen=True)
class RowEvidenceRule:
    """A list of objects whose named fields should share the anchor's visual line.

    `collection` is a dotted model path to a list, e.g. "items" or
    "invoice.line_items". `anchor` and `fields` are direct Evidenced members
    of its items. Rules are explicit for custom schemas; a list alone does
    not assert that an object's fields are printed together.

    Optional `column_headers` maps every named member, including the anchor,
    to exact header-label alternatives (case and whitespace insensitive).
    Only complete header rows and contiguous, fully aligned data rows qualify.
    Unavailable column evidence does not change a source verdict; a numeric
    quote aligned with a different configured header requires review.
    """

    collection: str
    anchor: str
    fields: tuple[str, ...]
    column_headers: Mapping[str, tuple[str, ...]] | None = None

    def __post_init__(self) -> None:
        if not self.collection or any(not _NAME.fullmatch(p) for p in self.collection.split(".")):
            raise ValueError("row rule collection must be a dotted model-field path")
        if not _NAME.fullmatch(self.anchor):
            raise ValueError("row rule anchor must name a direct field")
        if (
            isinstance(self.fields, str)
            or not self.fields
            or any(not _NAME.fullmatch(p) for p in self.fields)
            or self.anchor in self.fields
            or len(set(self.fields)) != len(self.fields)
        ):
            raise ValueError("row rule fields must be distinct direct fields, excluding the anchor")
        object.__setattr__(self, "fields", tuple(self.fields))
        if self.column_headers is not None:
            if not isinstance(self.column_headers, Mapping):
                raise ValueError("column headers must map field names to header labels")
            if set(self.column_headers) != {self.anchor, *self.fields}:
                raise ValueError("column headers must name the anchor and every row field")
            headers = {}
            seen = set()
            for name, labels in self.column_headers.items():
                if isinstance(labels, str) or not labels:
                    raise ValueError("each column needs a nonempty sequence of header labels")
                for label in labels:
                    if not isinstance(label, str) or not label.strip():
                        raise ValueError("column header labels must be nonempty strings")
                    normalized = " ".join(label.casefold().split())
                    if normalized in seen:
                        raise ValueError("column header labels must be distinct")
                    seen.add(normalized)
                headers[name] = tuple(labels)
            object.__setattr__(self, "column_headers", headers)


@dataclass(frozen=True)
class RowEvidenceCheck:
    field: str
    anchor: str
    status: Literal["same_line", "separate", "unavailable"]
    reason: str
    # Source status is captured before row and arithmetic checks affect the verdict.
    field_source_status: str | None
    anchor_source_status: str | None
    field_location: dict[str, Any] | None
    anchor_location: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_row_rules(data: BaseModel) -> tuple[RowEvidenceRule, ...]:
    if isinstance(data, Invoice):
        return (
            RowEvidenceRule(
                "line_items",
                "description",
                ("quantity", "unit_price", "amount"),
                column_headers={
                    "description": ("Description", "Item description"),
                    "quantity": ("Qty", "Quantity"),
                    "unit_price": ("Unit price",),
                    "amount": ("Amount", "Line total"),
                },
            ),
        )
    if isinstance(data, Receipt):
        return (RowEvidenceRule("items", "description", ("quantity", "amount")),)
    return ()


def configured_rows(
    data: BaseModel, rules: tuple[RowEvidenceRule, ...]
) -> dict[str, RowEvidenceRule]:
    """Expand declared collections; reject typos instead of silently running no check."""
    rows = {}
    collections = set()
    for rule in rules:
        if rule.collection in collections:
            raise ValueError(f"duplicate row rule for {rule.collection!r}")
        collections.add(rule.collection)
        collection: object = data
        for part in rule.collection.split("."):
            if not isinstance(collection, BaseModel) or part not in type(collection).model_fields:
                raise ValueError(f"row rule collection {rule.collection!r} does not exist")
            collection = getattr(collection, part)
        if not isinstance(collection, list):
            raise ValueError(f"row rule collection {rule.collection!r} must be a list")
        for index, item in enumerate(collection):
            prefix = f"{rule.collection}[{index}]"
            if not isinstance(item, BaseModel):
                raise ValueError(f"row rule item {prefix!r} must be a model")
            for name in (rule.anchor, *rule.fields):
                if name not in type(item).model_fields:
                    raise ValueError(f"row rule field {prefix}.{name} does not exist")
                value = getattr(item, name)
                if value is not None and not isinstance(value, Evidenced):
                    raise ValueError(f"row rule field {prefix}.{name} must be Evidenced or None")
            rows[prefix] = rule
    return rows


def _location(match: GroundingMatch | None) -> dict[str, Any] | None:
    if match is None:
        return None
    return {
        "page": match.page_number,
        "text": match.matched_text,
        "start": match.start,
        "end": match.end,
        "rects": [rect.to_dict() for rect in rects_for_match(match)],
    }


def check_row_field(
    field_path: str,
    anchor_path: str,
    field_result: FieldVerification | None,
    anchor_result: FieldVerification | None,
    field_match: GroundingMatch | None,
    anchor_match: GroundingMatch | None,
    *,
    anchor_trusted: bool,
) -> RowEvidenceCheck:
    status: Literal["same_line", "separate", "unavailable"] = "unavailable"
    if field_result is None:
        reason = f"{field_path} was not extracted"
    elif not anchor_trusted or anchor_match is None:
        reason = f"{anchor_path} has no independently supported, unedited source location"
    elif field_match is None or not field_match.is_strong or field_result.status != "verified":
        reason = f"{field_path} has no strongly grounded, value-supported source location"
    elif anchor_match.page_number != field_match.page_number:
        status = "separate"
        reason = (
            f"{field_path} is quoted from page {field_match.page_number}, but "
            f"{anchor_path} is on page {anchor_match.page_number}"
        )
    elif (
        unique_row_candidate([anchor_match], anchor_match) is None
        or unique_row_candidate([field_match], field_match) is None
    ):
        reason = "the quotes span multiple visual lines or have unusable word geometry"
    elif unique_row_candidate([field_match], anchor_match) is not None:
        status = "same_line"
        reason = (
            f"{field_path} and {anchor_path} share a visual line on page "
            f"{anchor_match.page_number}; this does not establish the column or field role"
        )
    else:
        status = "separate"
        reason = (
            f"{field_path} is quoted from a different visual line than {anchor_path} "
            f"on page {anchor_match.page_number}"
        )
    return RowEvidenceCheck(
        field=field_path,
        anchor=anchor_path,
        status=status,
        reason=reason,
        field_source_status=field_result.status.value if field_result else None,
        anchor_source_status=anchor_result.status.value if anchor_result else None,
        field_location=_location(field_match),
        anchor_location=_location(anchor_match),
    )
