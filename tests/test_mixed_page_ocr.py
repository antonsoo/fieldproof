"""Partial page recognition preserves native evidence and failure boundaries."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fieldproof.cli import app
from fieldproof.document import ocr
from fieldproof.document.limits import DocumentLimitError, DocumentLimits
from fieldproof.document.loader import load_pdf
from fieldproof.document.model import document_from_dict

INPUTS = Path(__file__).resolve().parents[1] / "studies/mixed-page-ocr/inputs"
runner = CliRunner()


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    runtime = pytest.importorskip("pytesseract")
    monkeypatch.setattr(ocr, "is_available", lambda: True)
    monkeypatch.setattr(runtime, "get_tesseract_version", lambda: "test-engine")
    return runtime


def data(words: list[str]) -> dict:
    return {
        "text": words,
        "left": [144] * len(words),
        "top": [104 + index * 40 for index in range(len(words))],
        "width": [100] * len(words),
        "height": [24] * len(words),
    }


@pytest.mark.parametrize(
    "kind,processed,native_number",
    [
        ("mixed", [2], 1),
        ("scan-first", [1], 2),
        ("blank-middle", [2, 3], 1),
    ],
)
def test_only_missing_pages_are_recognized_with_native_words_unchanged(
    kind: str,
    processed: list[int],
    native_number: int,
    engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def recognize(image, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return data([] if kind == "blank-middle" and len(calls) == 1 else ["Total", "123.45"])

    monkeypatch.setattr(engine, "image_to_data", recognize)
    path = INPUTS / f"{kind}.pdf"
    native = load_pdf(path)
    result = ocr.load_pdf_with_ocr(path, language="eng+fra", timeout=2)
    assert len(calls) == len(processed)
    assert all(call["lang"] == "eng+fra" and call["timeout"] == 2 for call in calls)
    assert asdict(result.page(native_number)) == asdict(native.page(native_number))
    assert result.ocr is not None and result.ocr.processed_pages == processed
    assert result.ocr.page_count == native.page_count
    assert result.ocr.empty_pages == ([2] if kind == "blank-middle" else [])
    assert document_from_dict(json.loads(json.dumps(asdict(result)))) == result
    for page in result.pages:
        assert all(page.text[word.start : word.end] == word.text for word in page.words)


def test_native_only_option_needs_no_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "is_available", lambda: False)
    native = load_pdf(INPUTS / "native.pdf")
    assert ocr.load_pdf_with_ocr(INPUTS / "native.pdf") == native
    assert native.ocr is None


@pytest.mark.parametrize(
    "limits",
    [
        DocumentLimits(max_words=7),
        DocumentLimits(max_text_chars=55),
    ],
)
def test_budgets_count_native_and_recognized_text_together(
    limits: DocumentLimits,
    engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        engine,
        "image_to_data",
        lambda *a, **kw: data(["Subtotal", "120.00", "Tax", "3.45", "Total", "123.45"]),
    )
    # Native and OCR populations each fit; their combination must not.
    native = load_pdf(INPUTS / "mixed.pdf", limits=limits)
    assert len(native.page(1).words) <= limits.max_words
    assert len(native.page(1).text) <= limits.max_text_chars
    with pytest.raises(DocumentLimitError, match="Combined native and OCR"):
        ocr.load_pdf_with_ocr(INPUTS / "mixed.pdf", limits=limits)


@pytest.mark.parametrize("command", ["extract", "verify"])
def test_missing_engine_preserves_prior_output(
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(ocr, "is_available", lambda: False)
    prior = tmp_path / "prior.json"
    path, fixture = INPUTS / "mixed.pdf", INPUTS / "mixed.json"
    prior.write_text(fixture.read_text() if command == "verify" else "previous result")
    before = prior.read_bytes()
    parameters = (
        ["extract", str(path), "--fixture", str(fixture)]
        if command == "extract"
        else ["verify", str(prior), str(path)]
    )
    output_option = ["--out", str(prior)] if command == "extract" else []
    result = runner.invoke(app, [*parameters, "--ocr-missing-pages", *output_option])
    assert result.exit_code == 1 and "OCR is not available" in result.output
    assert "Traceback" not in result.output
    assert prior.read_bytes() == before


@pytest.mark.parametrize("command", ["extract", "verify"])
def test_later_page_failure_discards_earlier_recognition(
    command: str,
    engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = 0

    def recognize(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("recognizer failed")
        return data(["Partial", "123.45"])

    monkeypatch.setattr(engine, "image_to_data", recognize)
    prior = tmp_path / "prior.json"
    path, fixture = INPUTS / "blank-middle.pdf", INPUTS / "blank-middle.json"
    prior.write_text(fixture.read_text() if command == "verify" else "previous result")
    before = prior.read_bytes()
    parameters = (
        ["extract", str(path), "--fixture", str(fixture)]
        if command == "extract"
        else ["verify", str(prior), str(path)]
    )
    output_option = ["--out", str(prior)] if command == "extract" else []
    result = runner.invoke(app, [*parameters, "--ocr-missing-pages", *output_option])
    assert result.exit_code == 1 and "OCR failed on page 3" in result.output
    assert calls == 2 and prior.read_bytes() == before


@pytest.mark.skipif(not ocr.is_available(), reason="actual Tesseract and OCR extra required")
@pytest.mark.parametrize(
    "kind,pages", [("mixed", [2]), ("scan-first", [1]), ("blank-middle", [2, 3])]
)
def test_actual_cli_recovers_totals_on_original_pages(
    kind: str, pages: list[int], tmp_path: Path
) -> None:
    path, fixture = INPUTS / f"{kind}.pdf", INPUTS / f"{kind}.json"
    output = tmp_path / "actual.json"
    for command in [
        ["extract", str(path), "--fixture", str(fixture)],
        ["verify", str(output), str(path)],
    ]:
        result = runner.invoke(app, [*command, "--ocr-missing-pages", "--out", str(output)])
        assert result.exit_code == 0, result.output
        report = json.loads(output.read_text())["report"]
        assert report["counts"] == {"verified": 6, "needs_review": 0, "unsupported": 0}
        assert report["ocr"]["processed_pages"] == pages
        totals_page = pages[-1]
        assert all(
            field["page"] == totals_page
            for field in report["fields"]
            if field["path"] in {"subtotal", "tax", "total"}
        )


@pytest.mark.skipif(not ocr.is_available(), reason="actual Tesseract and OCR extra required")
def test_all_scanned_provenance_and_native_fallback_keep_legacy_format() -> None:
    path = INPUTS / "all-scanned.pdf"
    old = ocr.load_scanned_pdf(path)
    new = ocr.load_pdf_with_ocr(path)
    assert new == old
    assert old.ocr is not None and "processed_pages" not in old.ocr.to_dict()
