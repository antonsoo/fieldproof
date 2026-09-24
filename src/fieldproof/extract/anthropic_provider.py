"""Anthropic-backed extractor using structured outputs (`messages.parse`).

No live network calls happen anywhere in this repository - this machine has
no `ANTHROPIC_API_KEY` configured, and CI never sets one. The unit tests
(`tests/test_extract_anthropic.py`) construct an `AnthropicExtractor` with a
mocked `anthropic.Anthropic` client and assert on the request shape (prompt
contents, schema passed through) and on response handling (including the
`parsed_output is None` error path), never on a real completion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from fieldproof.document.model import Document
from fieldproof.extract.base import ExtractionError, ExtractionResult

#: Anthropic's current most capable model (see the claude-api skill's model
#: table). Override via the `model` constructor argument (or the CLI's
#: `--model` flag) for a cheaper or faster one.
DEFAULT_MODEL = "claude-opus-5-5"

_SYSTEM_PROMPT = """You are a meticulous document-extraction assistant. You will be given \
the full text of a document, page by page, with each page's exact wording preserved below.

Extract the requested fields. For every field, you MUST provide:
- `value`: the extracted value, normalized to the requested type (ISO-8601 dates; plain \
numbers for money, with no currency symbol or thousands separator).
- `evidence`: one or more VERBATIM quotes copied character-for-character from the document \
text below that support this value. Never paraphrase, translate, reformat, or correct the \
quote - copy the exact substring as it appears, including its original punctuation and \
casing. If you cannot find text that supports a value, leave `evidence` empty rather than \
inventing a quote.
  - A short value (a bare number, a single word) can appear more than once in a document - a \
  quantity of "1" in a line-item table, for instance, is often not unique. If the value you're \
  quoting could plausibly appear elsewhere too, quote enough surrounding context to make it \
  unambiguous - for a table row, that usually means the whole row, e.g. "Fuel surcharge 1 \
  210.50 210.50" rather than just "1". If the value is already unique in the document (most \
  names, dates, and totals are), a short precise quote is fine.
- `page`: the 1-indexed page number the evidence came from.

If a field is genuinely absent from the document, use an empty string/list or omit it where \
the schema allows one - never guess a plausible-looking value that has no evidence on the \
page."""

T = TypeVar("T", bound=BaseModel)


@dataclass
class AnthropicExtractor:
    """Extracts a Pydantic schema from a `Document` via Claude's structured
    outputs. `client` is injectable for testing; when omitted, a default
    `anthropic.Anthropic()` is constructed lazily (so importing this module
    never requires credentials)."""

    model: str = DEFAULT_MODEL
    client: anthropic.Anthropic | None = None
    max_tokens: int = 16000

    def _get_client(self) -> anthropic.Anthropic:
        return self.client if self.client is not None else anthropic.Anthropic()

    def extract(self, document: Document, schema: type[T]) -> ExtractionResult:
        response = self._get_client().messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_prompt(document)}],
            output_format=schema,
        )
        data = response.parsed_output
        if data is None:
            raise ExtractionError(
                f"Claude did not return a parsed {schema.__name__} "
                f"(stop_reason={getattr(response, 'stop_reason', None)!r})"
            )
        return ExtractionResult(
            schema_name=schema.__name__,
            data=data,
            provider="anthropic",
            model=self.model,
        )


def _build_prompt(document: Document) -> str:
    parts = [f"Document: {document.source}\n"]
    for page in document.pages:
        parts.append(f"=== Page {page.number} ===\n{page.text}\n")
    return "\n".join(parts)
