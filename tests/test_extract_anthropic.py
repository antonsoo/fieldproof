"""The Claude provider over the real `anthropic` SDK.

The SDK is given an HTTP client whose transport answers in the Messages API's wire format
(a server-sent event stream), so the request these tests look at is the one the SDK sends,
and the reply the provider parses was assembled by the SDK's own stream code. No network
and no API key; nothing here was written by a model.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import anthropic
import pytest
from typer.testing import CliRunner

from fieldproof.cli import app
from fieldproof.document.loader import load_pdf
from fieldproof.extract.anthropic_provider import DEFAULT_MODEL, AnthropicExtractor
from fieldproof.extract.base import ExtractionError
from fieldproof.schemas import BUILTIN_SCHEMAS, Invoice

EXAMPLES = Path(__file__).parent.parent / "examples"


def _http() -> ModuleType:
    """The HTTP library the installed SDK is built on (httpx, or httpx2 in newer releases)."""
    for base in anthropic.DefaultHttpxClient.__mro__[1:]:
        root = base.__module__.split(".")[0]
        if root.startswith("httpx"):
            return importlib.import_module(root)
    raise RuntimeError("can't tell which HTTP library the anthropic SDK uses")


def _stream(text: str, stop_reason: str, model: str) -> bytes:
    """A Messages API event stream for a reply of one text block, cut into small deltas."""
    message = {
        "id": "msg_01",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 900, "output_tokens": 1},
    }
    events: list[dict[str, Any]] = [{"type": "message_start", "message": message}]
    if text or stop_reason != "refusal":
        events.append(
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            }
        )
        events.extend(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": text[i : i + 37]},
            }
            for i in range(0, len(text), 37)
        )
        events.append({"type": "content_block_stop", "index": 0})
    events.append(
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": 400},
        }
    )
    events.append({"type": "message_stop"})
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


class Api:
    """Stands in for api.anthropic.com: records each request, answers with `reply`."""

    def __init__(self, text: str = "", stop_reason: str = "end_turn", status: int = 200) -> None:
        self.text, self.stop_reason, self.status = text, stop_reason, status
        self.requests: list[dict[str, Any]] = []
        self.http = _http()

    def _handle(self, request: Any) -> Any:
        body = json.loads(request.content)
        self.requests.append(body)
        if self.status != 200:
            error = {
                "type": "error",
                "error": {"type": "overloaded_error", "message": "Overloaded"},
            }
            return self.http.Response(self.status, json=error)
        return self.http.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_stream(self.text, self.stop_reason, body["model"]),
        )

    def client(self) -> anthropic.Anthropic:
        transport = self.http.MockTransport(self._handle)
        return anthropic.Anthropic(
            api_key="test", http_client=self.http.Client(transport=transport), max_retries=0
        )


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / "fixtures" / f"{name}.json").read_text())["data"]


@pytest.mark.parametrize("name", sorted(BUILTIN_SCHEMAS))
def test_each_built_in_schema_is_sent_as_a_json_schema_and_the_reply_parsed(name: str) -> None:
    schema = BUILTIN_SCHEMAS[name]
    api = Api(json.dumps(_fixture(name)))
    document = load_pdf(EXAMPLES / f"{name}.pdf")

    result = AnthropicExtractor(client=api.client()).extract(document, schema)

    assert result.provider == "anthropic" and result.model == DEFAULT_MODEL
    assert isinstance(result.data, schema)
    assert result.data.model_dump(mode="json") == schema.model_validate(_fixture(name)).model_dump(
        mode="json"
    )

    (request,) = api.requests
    assert request["stream"] is True and request["model"] == DEFAULT_MODEL
    assert request["max_tokens"] == 16000
    # The document's own words are in the prompt, page by page.
    assert "=== Page 1 ===" in request["messages"][0]["content"]
    assert document.pages[0].text[:40] in request["messages"][0]["content"]
    # The schema travels as structured-output JSON Schema, closed to extra keys.
    output_format = request["output_config"]["format"]
    assert output_format["type"] == "json_schema"
    sent_schema = output_format["schema"]
    assert sent_schema["type"] == "object" and sent_schema["additionalProperties"] is False
    assert set(schema.model_fields) == set(sent_schema["properties"])


def test_model_and_max_tokens_reach_the_request() -> None:
    api = Api(json.dumps(_fixture("invoice")))
    extractor = AnthropicExtractor(model="claude-sonnet-5-5", max_tokens=32000, client=api.client())
    result = extractor.extract(load_pdf(EXAMPLES / "invoice.pdf"), Invoice)
    assert result.model == "claude-sonnet-5-5"
    assert (api.requests[0]["model"], api.requests[0]["max_tokens"]) == ("claude-sonnet-5-5", 32000)


def test_a_reply_cut_off_at_max_tokens_says_so() -> None:
    # A long invoice: the JSON stops in the middle of a field. The SDK's own `parse` helper
    # raises a pydantic "Invalid JSON: EOF while parsing a string" for this.
    cut = json.dumps(_fixture("invoice"))[:300]
    api = Api(cut, stop_reason="max_tokens")
    extractor = AnthropicExtractor(max_tokens=4000, client=api.client())
    with pytest.raises(ExtractionError) as excinfo:
        extractor.extract(load_pdf(EXAMPLES / "invoice.pdf"), Invoice)
    message = str(excinfo.value)
    assert "cut off at 4000 output tokens" in message
    assert "Invoice" in message and "--max-tokens" in message


def test_a_refusal_says_so() -> None:
    api = Api("", stop_reason="refusal")
    with pytest.raises(ExtractionError, match="declined to extract from this document"):
        AnthropicExtractor(client=api.client()).extract(load_pdf(EXAMPLES / "invoice.pdf"), Invoice)


def test_a_reply_that_is_not_the_schema_names_what_does_not_fit() -> None:
    api = Api(json.dumps({"vendor_name": "Acme"}))
    with pytest.raises(ExtractionError) as excinfo:
        AnthropicExtractor(client=api.client()).extract(load_pdf(EXAMPLES / "invoice.pdf"), Invoice)
    assert "Claude's reply does not match the Invoice schema: vendor_name: " in str(excinfo.value)

    api = Api("I'm sorry, I can't read this document.")
    with pytest.raises(
        ExtractionError, match=r"did not return a Invoice as JSON \(stop_reason='end_turn'\)"
    ):
        AnthropicExtractor(client=api.client()).extract(load_pdf(EXAMPLES / "invoice.pdf"), Invoice)


def test_an_api_error_is_an_extraction_error() -> None:
    api = Api(status=529)
    with pytest.raises(ExtractionError, match="the Anthropic API request failed: .*Overloaded"):
        AnthropicExtractor(client=api.client()).extract(load_pdf(EXAMPLES / "invoice.pdf"), Invoice)


def test_missing_credentials_are_named(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(variable, raising=False)
    api = Api(json.dumps(_fixture("invoice")))
    transport = api.http.MockTransport(api._handle)
    client = anthropic.Anthropic(http_client=api.http.Client(transport=transport), max_retries=0)
    with pytest.raises(ExtractionError, match="set ANTHROPIC_API_KEY"):
        AnthropicExtractor(client=client).extract(load_pdf(EXAMPLES / "invoice.pdf"), Invoice)
    assert api.requests == []  # nothing was sent without a key


def _patch_default_client(
    monkeypatch: pytest.MonkeyPatch, make: Callable[[], anthropic.Anthropic]
) -> None:
    monkeypatch.setattr(AnthropicExtractor, "_get_client", lambda self: make())


def test_cli_extracts_with_claude_and_passes_max_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = Api(json.dumps(_fixture("invoice")))
    _patch_default_client(monkeypatch, api.client)
    out = tmp_path / "result.json"
    result = CliRunner().invoke(
        app,
        [
            "extract",
            str(EXAMPLES / "invoice.pdf"),
            "--provider",
            "anthropic",
            "--max-tokens",
            "24000",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert api.requests[0]["max_tokens"] == 24000
    written = json.loads(out.read_text())
    assert written["provider"] == "anthropic" and written["schema"] == "invoice"
    assert written["report"]["counts"]["verified"] > 0


def test_cli_reports_a_cut_off_reply_in_one_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = Api(json.dumps(_fixture("invoice"))[:200], stop_reason="max_tokens")
    _patch_default_client(monkeypatch, api.client)
    result = CliRunner().invoke(
        app,
        [
            "extract",
            str(EXAMPLES / "invoice.pdf"),
            "--provider",
            "anthropic",
            "--out",
            str(tmp_path / "r.json"),
        ],
    )
    assert result.exit_code == 1
    assert "error: Claude's reply was cut off at 16000 output tokens" in result.output
    assert "Traceback" not in result.output
    assert not (tmp_path / "r.json").exists()
