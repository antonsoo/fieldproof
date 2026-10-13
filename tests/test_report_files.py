from __future__ import annotations

import errno
import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fieldproof import cli
from fieldproof._reports import write_report

runner = CliRunner()
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize("source", ["document", "fixture"])
@pytest.mark.parametrize("alias", ["direct", "symbolic", "hard"])
def test_extract_refuses_input_aliases_before_loading_or_calling_a_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, alias: str
) -> None:
    document = tmp_path / "document.pdf"
    fixture = tmp_path / "fixture.json"
    document.write_bytes(b"intentionally unreadable PDF")
    fixture.write_bytes(b"intentionally unreadable fixture")
    protected = document if source == "document" else fixture
    output = protected
    if alias != "direct":
        output = tmp_path / "output.json"
        if alias == "symbolic":
            output.symlink_to(protected)
        else:
            os.link(protected, output)

    def unexpected_load(path: Path) -> None:
        raise AssertionError("destination must be rejected before document/provider work")

    monkeypatch.setattr(cli, "_load_document", unexpected_load)
    command = ["extract", str(document), "--out", str(output)]
    command += ["--provider", "anthropic"] if source == "document" else ["--fixture", str(fixture)]
    result = runner.invoke(cli.app, command)
    assert result.exit_code == 2
    assert result.output.startswith("error: cannot write report:")
    assert document.read_bytes() == b"intentionally unreadable PDF"
    assert fixture.read_bytes() == b"intentionally unreadable fixture"


def test_verify_protects_pdf_before_reading_the_extraction(tmp_path: Path) -> None:
    document = tmp_path / "document.pdf"
    result = tmp_path / "result.json"
    document.write_bytes(b"source PDF")
    result.write_bytes(b"not JSON")
    invoked = runner.invoke(cli.app, ["verify", str(result), str(document), "--out", str(document)])
    assert invoked.exit_code == 2
    assert "report output must be distinct" in invoked.output
    assert document.read_bytes() == b"source PDF" and result.read_bytes() == b"not JSON"


@pytest.mark.parametrize("existing", [False, True])
def test_failed_replacement_preserves_old_report_and_removes_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    destination = tmp_path / "report.json"
    previous = b'{"previous": true}\n'
    if existing:
        destination.write_bytes(previous)

    def refused_replace(source: Path, target: Path) -> None:
        assert source.read_text() == '{"replacement": true}'
        raise OSError(errno.EACCES, "replacement denied")

    monkeypatch.setattr("fieldproof._reports.os.replace", refused_replace)
    with pytest.raises(OSError, match="replacement denied"):
        write_report(destination, '{"replacement": true}', ())
    assert sorted(p.name for p in tmp_path.iterdir()) == ([destination.name] if existing else [])
    if existing:
        assert destination.read_bytes() == previous


def test_cli_write_failure_is_one_error_and_keeps_the_previous_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "report.json"
    destination.write_bytes(b"previous review")

    def refused_sync(fd: int) -> None:
        raise OSError(errno.EIO, "flush failed")

    monkeypatch.setattr("fieldproof._reports.os.fsync", refused_sync)
    result = runner.invoke(
        cli.app,
        [
            "extract",
            str(EXAMPLES / "invoice.pdf"),
            "--fixture",
            str(EXAMPLES / "fixtures/invoice.json"),
            "--out",
            str(destination),
        ],
    )
    assert result.exit_code == 2
    assert result.output.startswith("error: cannot write report:")
    assert "Traceback" not in result.output
    assert destination.read_bytes() == b"previous review"
    assert list(tmp_path.iterdir()) == [destination]


def test_explicit_verify_in_place_remains_supported_and_private(tmp_path: Path) -> None:
    destination = tmp_path / "result.json"
    destination.write_bytes((EXAMPLES / "fixtures/invoice.json").read_bytes())
    result = runner.invoke(
        cli.app,
        ["verify", str(destination), str(EXAMPLES / "invoice.pdf"), "--out", str(destination)],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(destination.read_bytes())["report"]["counts"] == {
        "verified": 21,
        "needs_review": 3,
        "unsupported": 1,
    }
    if os.name == "posix":
        assert destination.stat().st_mode & 0o777 == 0o600


def test_write_rechecks_an_alias_created_after_preflight(tmp_path: Path) -> None:
    from fieldproof._reports import check_report_destination

    source = tmp_path / "document.pdf"
    source.write_bytes(b"original PDF")
    destination = tmp_path / "report.json"
    check_report_destination(destination, (source,))
    os.link(source, destination)
    with pytest.raises(OSError, match="must be distinct"):
        write_report(destination, "replacement", (source,))
    assert source.read_bytes() == b"original PDF"
