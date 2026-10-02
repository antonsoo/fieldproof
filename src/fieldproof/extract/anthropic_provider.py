"""Anthropic-backed extractor using structured outputs.

The request carries the schema as `output_config.format` (a JSON Schema the
SDK derives from the Pydantic model with `anthropic.transform_schema`), so
Claude's reply is constrained to it. The reply is streamed and collected:
a long extraction can run past the time a plain request is allowed, and the
SDK refuses a non-streaming call it expects to.

A constrained reply can still fail to be the schema in two ways, and both
are told from the reply's `stop_reason` rather than from a JSON error: it
was cut off at `max_tokens` (an invoice with hundreds of line items), or the
model declined (`refusal`).

No live network calls happen anywhere in this repository - this machine has
no `ANTHROPIC_API_KEY` configured, and CI never sets one.
`tests/test_extract_anthropic.py` runs the real `anthropic` SDK over a mocked
HTTP transport that answers in the Messages API's wire format, so the
request it checks is the one the SDK really sends and the replies are parsed
by the SDK's own code; no completion in those tests came from a model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel

from fieldproof.document.model import Document
from fieldproof.extract.base import ExtractionError, ExtractionResult, validate_data

#: Claude Opus 5.5, the current Opus model. Override via the `model`
#: constructor argument (or the CLI's `--model` flag), e.g. with
#: `claude-sonnet-5-5` for a cheaper and faster one.
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
        # Typed loosely: the SDK's TypedDicts for this parameter have changed names between
        # the releases this works with.
        output_config: Any = {
            "format": {"type": "json_schema", "schema": anthropic.transform_schema(schema)}
        }
        try:
            with self._get_client().messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _build_prompt(document)}],
                output_config=output_config,
            ) as stream:
                message = stream.get_final_message()
        except anthropic.AnthropicError as exc:
            raise ExtractionError(f"the Anthropic API request failed: {exc}") from exc
        except TypeError as exc:
            # How the SDK reports that it found no API key or token to send.
            if "authentication method" not in str(exc):
                raise
            raise ExtractionError("no Anthropic credentials found: set ANTHROPIC_API_KEY") from exc
        return ExtractionResult(
            schema_name=schema.__name__,
            data=_parse_reply(message, schema, self.max_tokens),
            provider="anthropic",
            model=self.model,
        )


def _parse_reply(message: Any, schema: type[T], max_tokens: int) -> T:
    """Claude's reply as an instance of `schema`, or an `ExtractionError` that says why it
    isn't one."""
    stop_reason = getattr(message, "stop_reason", None)
    if stop_reason == "max_tokens":
        raise ExtractionError(
            f"Claude's reply was cut off at {max_tokens} output tokens, before the "
            f"{schema.__name__} was complete; raise the limit (--max-tokens) or extract a "
            "shorter document"
        )
    if stop_reason == "refusal":
        raise ExtractionError(
            "Claude declined to extract from this document (stop_reason 'refusal')"
        )
    text = "".join(
        block.text
        for block in getattr(message, "content", [])
        if getattr(block, "type", "") == "text"
    )
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise ExtractionError(
            f"Claude did not return a {schema.__name__} as JSON (stop_reason={stop_reason!r})"
        ) from exc
    return validate_data(payload, schema, "Claude's reply")


def _build_prompt(document: Document) -> str:
    parts = [f"Document: {document.source}\n"]
    for page in document.pages:
        parts.append(f"=== Page {page.number} ===\n{page.text}\n")
    return "\n".join(parts)
