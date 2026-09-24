"""Fixture extractor: replays a stored JSON extraction instead of calling a
live provider.

This is what the test suite, the CI pipeline, and the static Pages demo all
use - none of them have an API key or network access, and none of them
should need one to exercise grounding, verification, or the review UI. A
fixture is exactly the `ExtractionResult.to_dict()` shape a real provider
would have produced.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from fieldproof.document.model import Document
from fieldproof.extract.base import ExtractionResult

T = TypeVar("T", bound=BaseModel)


@dataclass
class FixtureExtractor:
    """Loads `fixture_path` (JSON) and validates it against the requested
    schema. The document argument is accepted (to satisfy the `Extractor`
    protocol) but not read - the fixture is expected to already match the
    document it stands in for. If it doesn't, grounding will simply report
    the mismatched fields as unsupported, which is a legitimate way to
    exercise that path in tests."""

    fixture_path: str | Path

    def extract(self, document: Document, schema: type[T]) -> ExtractionResult:
        del document  # unused: part of the Extractor protocol
        raw = json.loads(Path(self.fixture_path).read_text(encoding="utf-8"))
        payload = raw.get("data", raw)
        data = schema.model_validate(payload)
        return ExtractionResult(
            schema_name=schema.__name__,
            data=data,
            provider="fixture",
            model=raw.get("model", str(self.fixture_path)),
        )
