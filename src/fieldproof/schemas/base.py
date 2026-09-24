"""The `Evidenced[T]` wrapper and the generic walker every other stage uses.

fieldproof's trust story only works if grounding and verification can find
*every* extracted value in *any* schema, including one a user brings
themselves - so instead of hand-writing per-schema traversal, every leaf
value is wrapped in `Evidenced[T]` and `iter_evidenced_fields` walks an
arbitrary Pydantic model (nested models, lists of models) collecting them by
dotted path. Grounding and verification are written once, against this
walker, and never against Invoice/Receipt/Contract by name.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", str, float, bool)


class Evidenced(BaseModel, Generic[T]):
    """A single extracted value plus the verbatim quote(s) that support it.

    `evidence` holds exact substrings the model claims to have read on the
    page - grounding (`fieldproof.ground`) locates them in the real page
    text, and verification (`fieldproof.verify`) checks they actually
    support `value`. An empty `evidence` list means the model supplied a
    value with no citation, which verification treats as `unsupported`.
    """

    value: T
    evidence: list[str] = Field(default_factory=list)
    page: int | None = Field(default=None, description="1-indexed page the evidence was found on")


def iter_evidenced_fields(model: BaseModel, prefix: str = "") -> Iterator[tuple[str, Evidenced]]:
    """Yield `(dotted_path, Evidenced)` for every `Evidenced` leaf under `model`,
    recursing into nested `BaseModel`s and lists of them (e.g. line items)."""
    for name, value in model:
        path = f"{prefix}.{name}" if prefix else name
        yield from _walk_value(path, value)


def _walk_value(path: str, value: object) -> Iterator[tuple[str, Evidenced]]:
    if isinstance(value, Evidenced):
        yield path, value
    elif isinstance(value, BaseModel):
        yield from iter_evidenced_fields(value, path)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _walk_value(f"{path}[{i}]", item)
