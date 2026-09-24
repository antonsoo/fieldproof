"""The provider-agnostic extractor interface and result envelope."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from fieldproof.document.model import Document

T = TypeVar("T", bound=BaseModel)


class ExtractionError(RuntimeError):
    """Raised when a provider's response can't be turned into the schema."""


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
    def from_dict(cls, raw: dict[str, Any], schema: type[T]) -> ExtractionResult:
        return cls(
            schema_name=raw.get("schema", schema.__name__),
            data=schema.model_validate(raw["data"]),
            provider=raw.get("provider", "unknown"),
            model=raw.get("model"),
        )


class Extractor(Protocol):
    """Anything that can turn a `Document` into a schema instance. Both
    `AnthropicExtractor` and `FixtureExtractor` implement this without a
    shared base class - it's a structural protocol so a third-party
    extractor doesn't need to import fieldproof internals to conform."""

    def extract(self, document: Document, schema: type[T]) -> ExtractionResult: ...
