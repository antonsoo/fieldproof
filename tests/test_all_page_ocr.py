"""Rendered evidence is an explicit choice, never a silent native/OCR mixture."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from test_mixed_page_ocr import data
from test_mixed_page_ocr import engine as engine
from typer.testing import CliRunner

from fieldproof.cli import app
from fieldproof.document import ocr
from fieldproof.document.model import document_from_dict

STUDY = Path(__file__).resolve().parents[1] / "studies/form-appearances"
MIXED = Path(__file__).resolve().parents[1] / "studies/mixed-page-ocr/inputs/mixed.pdf"
runner = CliRunner()


def test_all_pages_replace_native_words_and_preserve_page_identity(
    engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def recognize(image, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return data(["Rendered", "$100.00"] if len(calls) == 1 else [])

    def native(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("all-page OCR must not consult a native text layer")

    monkeypatch.setattr(engine, "image_to_data", recognize)
    monkeypatch.setattr(ocr, "load_pdf", native)
    document = ocr.load_pdf_with_ocr(MIXED, mode="all", language="eng+fra", timeout=2)
    assert document.page(1).text == "Rendered $100.00"
    assert document.page(2).text == "" and document.page_count == 2
    assert len(calls) == 2
    assert all(c["lang"] == "eng+fra" and c["timeout"] == 2 for c in calls)
    assert document.ocr is not None
    assert document.ocr.processed_pages == [1, 2] and document.ocr.empty_pages == [2]
    assert "replaces native text" in document.ocr.note
    assert document_from_dict(json.loads(json.dumps(asdict(document)))) == document


@pytest.mark.parametrize("command", ["extract", "verify"])
def test_cli_all_pages_can_ground_a_rendered_form_value(
    command: str,
    engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        engine, "image_to_data", lambda *a, **kw: data(["Authorized", "total:", "$100.00"])
    )
    claim = json.loads((STUDY / "claim.json").read_text())
    claim["data"]["total"] = {"value": 100, "evidence": ["Authorized total: $100.00"]}
    fixture = tmp_path / "claim.json"
    fixture.write_text(json.dumps(claim))
    output = tmp_path / "result.json"
    pdf = str(STUDY / "fixtures/covered-native-total.pdf")
    arguments = (
        ["extract", pdf, "--fixture", str(fixture)]
        if command == "extract"
        else ["verify", str(fixture), pdf]
    )
    result = runner.invoke(app, [*arguments, "--ocr-all-pages", "--out", str(output)])
    assert result.exit_code == 0, result.output
    report = json.loads(output.read_text())["report"]
    total = next(f for f in report["fields"] if f["path"] == "total")
    assert total["status"] == "verified" and total["matched_text"] == "Authorized total: $100.00"
    assert report["ocr"]["processed_pages"] == [1]
    assert "All-page OCR" in result.output and "replaces native text" in report["ocr"]["note"]


@pytest.mark.parametrize("command", ["extract", "verify"])
def test_explicit_all_page_mode_does_not_fall_back_when_engine_is_missing(
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(ocr, "is_available", lambda: False)
    prior = tmp_path / "prior.json"
    original = (STUDY / "claim.json").read_bytes()
    prior.write_bytes(original)
    pdf = str(STUDY / "fixtures/covered-native-total.pdf")
    args = (
        ["extract", pdf, "--fixture", str(STUDY / "claim.json")]
        if command == "extract"
        else ["verify", str(prior), pdf]
    )
    result = runner.invoke(app, [*args, "--ocr-all-pages", "--out", str(prior)])
    assert result.exit_code == 1 and "OCR is not available" in result.output
    assert prior.read_bytes() == original


def test_conflicting_page_choices_leave_output_untouched(tmp_path: Path) -> None:
    prior = tmp_path / "prior.json"
    original = (STUDY / "claim.json").read_bytes()
    prior.write_bytes(original)
    result = runner.invoke(
        app, ["verify", str(prior), str(MIXED), "--ocr-all-pages", "--ocr-missing-pages"]
    )
    assert result.exit_code == 2 and "choose either" in result.output
    assert prior.read_bytes() == original


def test_unknown_mode_is_rejected_before_pdf_or_engine_work() -> None:
    with pytest.raises(ValueError, match="OCR mode"):
        ocr.load_pdf_with_ocr(b"not a PDF", mode="native")  # type: ignore[arg-type]
