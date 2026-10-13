"""The `Evidenced[T]` wrapper and the generic walker every other stage uses.

fieldproof's trust story only works if grounding and verification can find
*every* extracted value in *any* schema, including one a user brings
themselves - so instead of hand-writing per-schema traversal, every leaf
value is wrapped in `Evidenced[T]` and `iter_evidenced_fields` walks nested
models, lists, tuples and string-keyed mappings, collecting them by distinct
paths. Grounding and verification are written once, against this
walker, and never against Invoice/Receipt/Contract by name.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
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

    Verification supports string, integer, float and boolean values. Put
    containers outside the wrapper so each claim has its own evidence. An
    absent optional claim is `Evidenced[T] | None`, not `Evidenced[T | None]`
    holding a null value; present wrappers with unsupported values raise a
    field-specific `ValueError` from `verify`.
    """

    value: T
    evidence: list[str] = Field(default_factory=list)
    page: int | None = Field(default=None, description="1-indexed page the evidence was found on")


class EvidencedDate(Evidenced[str]):
    """A claimed calendar date in YYYY-MM-DD format, checked against its quote.

    The original string is retained even when invalid: verification reports
    the problem instead of normalizing or discarding the supplied claim.
    """


class EvidencedText(Evidenced[str]):
    """Literal text, even when its field name contains a word such as date."""


def iter_evidenced_fields(model: BaseModel, prefix: str = "") -> Iterator[tuple[str, Evidenced]]:
    """Yield `(path, Evidenced)` through models, ordered sequences and mappings.

    Model identifiers use dots; sequence positions use numeric brackets.
    Mapping keys and non-identifier model names use JSON-quoted brackets so
    punctuation cannot collide with a nested field or sequence position.
    """
    for name, value in model:
        if name.isidentifier():
            path = f"{prefix}.{name}" if prefix else name
        else:
            path = f"{prefix}[{json.dumps(name)}]"
        yield from _walk_value(path, value)


def _walk_value(path: str, value: object) -> Iterator[tuple[str, Evidenced]]:
    if isinstance(value, Evidenced):
        yield path, value
    elif isinstance(value, BaseModel):
        yield from iter_evidenced_fields(value, path)
    elif isinstance(value, list | tuple):
        for i, item in enumerate(value):
            yield from _walk_value(f"{path}[{i}]", item)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(
                    f"mapping at {path!r} must use string keys, not {type(key).__name__}"
                )
            yield from _walk_value(f"{path}[{json.dumps(key)}]", item)
