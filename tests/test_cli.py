from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fieldproof.cli import app
from fieldproof.extract.base import ExtractionError

runner = CliRunner()

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def test_extract_then_verify_round_trips_the_schema_name(tmp_path: Path) -> None:
    """Regression test: `extract` used to write result.json's "schema" as
    the Pydantic class name (e.g. "Invoice"), but `verify` looked it up
    against the lowercase registry keys ("invoice") - so re-verifying your
    own CLI output always failed. `extract` now writes the registry key."""
    out = tmp_path / "result.json"
    result = runner.invoke(
        app,
        [
            "extract",
            str(EXAMPLES_DIR / "invoice.pdf"),
            "--schema",
            "invoice",
            "--provider",
            "fixture",
            "--fixture",
            str(EXAMPLES_DIR / "fixtures" / "invoice.json"),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text())["schema"] == "invoice"

    verify_result = runner.invoke(app, ["verify", str(out), str(EXAMPLES_DIR / "invoice.pdf")])
    assert verify_result.exit_code == 0, verify_result.output
    assert "unsupported" in verify_result.output


def test_verify_accepts_a_class_name_schema_too(tmp_path: Path) -> None:
    """External tools producing their own result.json won't know fieldproof's
    registry keys and may reach for the Pydantic class name instead - that
    should still resolve (see fieldproof.schemas.resolve_schema)."""
    raw = json.loads((EXAMPLES_DIR / "fixtures" / "invoice.json").read_text())
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps({"schema": "Invoice", "data": raw["data"]}))

    result = runner.invoke(app, ["verify", str(result_path), str(EXAMPLES_DIR / "invoice.pdf")])
    assert result.exit_code == 0, result.output


def test_verify_rejects_unknown_schema(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps({"schema": "not-a-real-schema", "data": {}}))

    result = runner.invoke(app, ["verify", str(result_path), str(EXAMPLES_DIR / "invoice.pdf")])
    assert result.exit_code == 2
    assert "not-a-real-schema" in result.output


def test_extract_rejects_unknown_schema(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "extract",
            str(EXAMPLES_DIR / "invoice.pdf"),
            "--schema",
            "not-a-schema",
            "--out",
            str(tmp_path / "out.json"),
        ],
    )
    assert result.exit_code == 2


def test_extract_fixture_provider_requires_fixture_flag(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "extract",
            str(EXAMPLES_DIR / "invoice.pdf"),
            "--schema",
            "invoice",
            "--provider",
            "fixture",
            "--out",
            str(tmp_path / "out.json"),
        ],
    )
    assert result.exit_code == 2


def test_extract_accepts_a_model_override_flag() -> None:
    result = runner.invoke(app, ["extract", "--help"])
    assert result.exit_code == 0
    assert "--model" in result.output


def test_version_flag() -> None:
    import fieldproof

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"fieldproof {fieldproof.__version__}"


def _one_line_error(result) -> str:  # type: ignore[no-untyped-def]
    """The command failed the way a command should: no traceback, one `error:` line."""
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert result.exit_code in (1, 2)
    message = result.output.strip()
    assert message.startswith("error: ") and "\n" not in message, message
    return message


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("{ not json", "result.json is not valid JSON (line 1, column 3"),
        ("[]", "result.json must hold a JSON object, not list"),
        ('{"schema": 5, "data": {}}', 'result.json\'s "schema" is 5; must name one of'),
        ('{"schema": "invoice"}', 'result.json has no "data" object'),
        ('{"schema": "invoice", "data": {"total": "x"}}', "does not match the Invoice schema"),
    ],
)
def test_verify_explains_a_result_it_cannot_read(
    tmp_path: Path, content: str, expected: str
) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text(content)
    result = runner.invoke(app, ["verify", str(result_path), str(EXAMPLES_DIR / "invoice.pdf")])
    assert expected in _one_line_error(result)
    assert result.exit_code == 2
    assert result_path.read_text() == content  # and it left the file alone


def test_a_file_that_is_not_a_pdf_is_a_one_line_error(tmp_path: Path) -> None:
    not_a_pdf = tmp_path / "notes.pdf"
    not_a_pdf.write_text("just some text")
    fixture = str(EXAMPLES_DIR / "fixtures" / "invoice.json")
    out = tmp_path / "out.json"
    extract = runner.invoke(
        app, ["extract", str(not_a_pdf), "--fixture", fixture, "--out", str(out)]
    )
    assert "could not read" in _one_line_error(extract) and "as a PDF" in extract.output
    verify = runner.invoke(app, ["verify", fixture, str(not_a_pdf), "--out", str(out)])
    assert "could not read" in _one_line_error(verify)
    assert not out.exists()


def test_extract_explains_a_fixture_it_cannot_use(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text('{"data": {"vendor_name": null}}')
    out = tmp_path / "out.json"
    result = runner.invoke(
        app,
        [
            "extract",
            str(EXAMPLES_DIR / "invoice.pdf"),
            "--fixture",
            str(fixture),
            "--out",
            str(out),
        ],
    )
    assert "fixture.json does not match the Invoice schema" in _one_line_error(result)
    assert not out.exists()


def test_a_provider_failure_is_a_one_line_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _NoCredentials:
        def __init__(self, model: str) -> None:
            del model

        def extract(self, document: object, schema: object) -> None:
            raise ExtractionError("no Anthropic credentials found: set ANTHROPIC_API_KEY")

    monkeypatch.setattr("fieldproof.cli.AnthropicExtractor", _NoCredentials)
    out = tmp_path / "out.json"
    result = runner.invoke(
        app,
        [
            "extract",
            str(EXAMPLES_DIR / "invoice.pdf"),
            "--provider",
            "anthropic",
            "--out",
            str(out),
        ],
    )
    assert "set ANTHROPIC_API_KEY" in _one_line_error(result)
    assert not out.exists()
