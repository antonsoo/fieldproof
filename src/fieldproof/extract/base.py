"""The provider-agnostic extractor interface and result envelope."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from fieldproof.document.model import Document

T = TypeVar("T", bound=BaseModel)


class ExtractionError(RuntimeError):
    """Raised when an extraction can't be turned into the schema: a provider's
    response, or a stored result that isn't JSON or doesn't have the schema's
    shape. The message is written for the person who supplied the file."""


def _decode(content: bytes) -> str:
    """A JSON file's text as editors and shells on Windows save it: UTF-8, with or without a
    byte-order mark (Notepad's "UTF-8 with BOM", PowerShell's `-Encoding utf8`), or UTF-16
    with one (PowerShell's `>`)."""
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16")
    return content.decode("utf-8-sig")


def read_extraction_json(content: str | bytes, source: str) -> dict[str, Any]:
    """Parse a stored extraction (a fixture, or another tool's `result.json`).
    `source` names the file in the error."""
    try:
        text = _decode(content) if isinstance(content, bytes) else content
        raw = json.loads(text)
    except UnicodeDecodeError as exc:
        raise ExtractionError(f"{source} is not UTF-8 text") from exc
    except json.JSONDecodeError as exc:
        raise ExtractionError(
            f"{source} is not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg})"
        ) from exc
    if not isinstance(raw, dict):
        raise ExtractionError(f"{source} must hold a JSON object, not {type(raw).__name__}")
    return raw


def validate_data(payload: Any, schema: type[T], source: str) -> T:
    """`payload` as an instance of `schema`, or an `ExtractionError` that
    lists what doesn't fit, field by field, instead of pydantic's full report."""
    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(part) for part in error['loc']) or 'data'}: {error['msg']}"
            for error in exc.errors()
        ]
        shown = "; ".join(problems[:3])
        more = f" (and {len(problems) - 3} more)" if len(problems) > 3 else ""
        raise ExtractionError(
            f"{source} does not match the {schema.__name__} schema: {shown}{more}"
        ) from exc


def _text_or(value: Any, default: str | None) -> str | None:
    return value if isinstance(value, str) else default


@dataclass
class ExtractionResult:
    """A schema instance plus provenance - which provider/model produced it,
    so `result.json` is self-describing when it's re-verified later."""

    schema_name: str
    data: BaseModel
    provider: str
    model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema_name,
            "provider": self.provider,
            "model": self.model,
            "data": self.data.model_dump(mode="json"),
        }

    @classmethod
    def from_dict(
        cls, raw: dict[str, Any], schema: type[T], *, source: str = "the result"
    ) -> ExtractionResult:
        if "data" not in raw:
            raise ExtractionError(f'{source} has no "data" object')
        return cls(
            schema_name=_text_or(raw.get("schema"), None) or schema.__name__,
            data=validate_data(raw["data"], schema, source),
            provider=_text_or(raw.get("provider"), None) or "unknown",
            model=_text_or(raw.get("model"), None),
        )


class Extractor(Protocol):
    """Anything that can turn a `Document` into a schema instance. Both
    `AnthropicExtractor` and `FixtureExtractor` implement this without a
    shared base class - it's a structural protocol so a third-party
    extractor doesn't need to import fieldproof internals to conform."""

    def extract(self, document: Document, schema: type[T]) -> ExtractionResult: ...
