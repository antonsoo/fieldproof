"""Scanned input reaches OCR; failures never leave a partial verified result."""

from __future__ import annotations

import io
import json
from dataclasses import asdict
from pathlib import Path

import pytest
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from typer.testing import CliRunner

from fieldproof.cli import app
from fieldproof.document import ocr
from fieldproof.document.limits import DocumentLimitError, DocumentLimits
from fieldproof.document.loader import EmptyDocumentError, load_pdf
from fieldproof.document.model import document_from_dict
from fieldproof.document.render import render_page_png
from fieldproof.extract.fixture_provider import FixtureExtractor
from fieldproof.schemas.invoice import Invoice
from fieldproof.server.pdf_work import verify_server_data
from fieldproof.verify.engine import verify

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
runner = CliRunner()


@pytest.fixture
def scan(tmp_path: Path) -> Path:
    # First page intentionally blank: retained coordinates must still name page 2.
    pytest.importorskip("PIL")
    path = tmp_path / "scan.pdf"
    canvas = Canvas(str(path), pagesize=(612, 792), invariant=1)
    canvas.showPage()
    canvas.drawImage(
        ImageReader(io.BytesIO(render_page_png(EXAMPLES / "invoice.pdf", 1))),
        0,
        0,
        width=612,
        height=792,
    )
    canvas.save()
    return path


@pytest.fixture
def fake_engine(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    engine = pytest.importorskip("pytesseract")
    monkeypatch.setattr(ocr, "is_available", lambda: True)
    monkeypatch.setattr(engine, "get_tesseract_version", lambda: "test-engine")
    return engine


def test_native_cli_never_requires_ocr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("native PDF must not run OCR")

    monkeypatch.setattr(ocr, "load_scanned_pdf", unexpected)
    out = tmp_path / "native.json"
    result = runner.invoke(
        app,
        [
            "extract",
            str(EXAMPLES / "invoice.pdf"),
            "--fixture",
            str(EXAMPLES / "fixtures/invoice.json"),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "OCR:" not in result.output
    assert "ocr" not in json.loads(out.read_text())["report"]


@pytest.mark.parametrize("command", ["extract", "verify"])
def test_missing_ocr_explained_without_overwriting_output(
    scan: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    monkeypatch.setattr(ocr, "is_available", lambda: False)
    out = tmp_path / "existing.json"
    out.write_text("keep this previous result")
    fixture = str(EXAMPLES / "fixtures/invoice.json")
    args = (
        ["extract", str(scan), "--fixture", fixture]
        if command == "extract"
        else ["verify", fixture, str(scan)]
    )
    result = runner.invoke(app, [*args, "--out", str(out)])
    assert result.exit_code == 1
    assert "install the 'ocr' extra" in result.output and "Tesseract binary" in result.output
    assert "Traceback" not in result.output
    assert out.read_text() == "keep this previous result"


def test_ocr_keeps_all_pages_offsets_and_provenance(scan: Path, fake_engine, monkeypatch):  # type: ignore[no-untyped-def]
    calls = []

    def recognize(image, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        words = [] if len(calls) == 1 else ["Northwind", "123.45"]
        return {
            "text": words,
            "left": [144, 300],
            "top": [104, 104],
            "width": [132, 90],
            "height": [24, 24],
        }

    monkeypatch.setattr(fake_engine, "image_to_data", recognize)
    document = ocr.load_scanned_pdf(scan, language="eng+fra", timeout=2)
    assert document.source == str(scan)
    assert document.page_count == 2 and document.pages[0].words == []
    page = document.page(2)
    assert page.text == "Northwind 123.45"
    assert [(w.start, w.end) for w in page.words] == [(0, 9), (10, 16)]
    assert page.words[0].bbox.to_dict() == {"x0": 72, "top": 52, "x1": 138, "bottom": 64}
    assert all(page.text[w.start : w.end] == w.text for w in page.words)
    assert all(call["lang"] == "eng+fra" and call["timeout"] == 2 for call in calls)
    assert document.ocr is not None and document.ocr.empty_pages == [1]
    assert document_from_dict(json.loads(json.dumps(asdict(document)))) == document
    data = FixtureExtractor(EXAMPLES / "fixtures/invoice.json").extract(document, Invoice).data
    report = verify(data, document)
    assert report.to_dict()["ocr"] == document.ocr.to_dict()
    assert verify_server_data("invoice", data, document).to_dict() == report.to_dict()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_timeout_cannot_disable_the_bound(scan: Path, timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout"):
        ocr.load_scanned_pdf(scan, timeout=timeout)


def test_wrong_page_count_cannot_silently_omit_a_page(scan: Path, fake_engine):  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="does not match"):
        ocr.load_scanned_pdf(scan, 1)


@pytest.mark.parametrize("limits", [DocumentLimits(max_pages=1), DocumentLimits(max_pixels=10)])
def test_geometry_checked_before_recognition(scan: Path, fake_engine, monkeypatch, limits):  # type: ignore[no-untyped-def]
    def unexpected(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("should fail before recognition")

    monkeypatch.setattr(fake_engine, "image_to_data", unexpected)
    with pytest.raises(DocumentLimitError):
        ocr.load_scanned_pdf(scan, limits=limits)


def test_no_words_is_not_a_successful_ocr_document(scan: Path, fake_engine, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(fake_engine, "image_to_data", lambda *a, **kw: {"text": []})
    with pytest.raises(EmptyDocumentError, match="recognized no words"):
        ocr.load_scanned_pdf(scan)


def test_timeout_keeps_previous_result(scan: Path, fake_engine, monkeypatch, tmp_path):  # type: ignore[no-untyped-def]
    def timeout(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(fake_engine, "image_to_data", timeout)
    out = tmp_path / "prior.json"
    out.write_bytes((EXAMPLES / "fixtures/invoice.json").read_bytes())
    before = out.read_bytes()
    result = runner.invoke(app, ["verify", str(out), str(scan)])
    assert result.exit_code == 1 and "OCR failed on page 1" in result.output
    assert out.read_bytes() == before


@pytest.mark.skipif(not ocr.is_available(), reason="real Tesseract and OCR extra required")
def test_real_tesseract_extract_and_reverify(scan: Path, tmp_path: Path) -> None:
    with pytest.raises(EmptyDocumentError):
        load_pdf(scan)
    out = tmp_path / "actual.json"
    result = runner.invoke(
        app,
        [
            "extract",
            str(scan),
            "--fixture",
            str(EXAMPLES / "fixtures/invoice.json"),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    raw = json.loads(out.read_text())
    assert raw["report"]["ocr"]["empty_pages"] == [1]
    assert raw["report"]["counts"]["verified"] > 0
    assert all(field["page"] in (None, 2) for field in raw["report"]["fields"])
    assert "Grounding checks the text recognized by OCR" in result.output
    repeated = runner.invoke(app, ["verify", str(out), str(scan)])
    assert repeated.exit_code == 0, repeated.output
    assert json.loads(out.read_text()) == raw
