from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fieldproof.cli import app

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
