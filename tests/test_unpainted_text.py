"""Actual PDFs whose extractable text and painted evidence disagree."""

from __future__ import annotations

import importlib.util
import io
import json
from dataclasses import asdict
from pathlib import Path

import pytest
from pydantic import BaseModel
from reportlab.pdfgen.canvas import Canvas

from fieldproof.document.loader import load_pdf
from fieldproof.document.model import document_from_dict
from fieldproof.schemas import Evidenced
from fieldproof.verify import verify

STUDY = Path(__file__).parents[1] / "studies/unpainted-text"


def test_all_authored_rendering_mode_controls_after_worker_transport() -> None:
    spec = importlib.util.spec_from_file_location("unpainted_replay", STUDY / "replay.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.replay()
    assert result["claims"] == 46
    assert result["conservative_stroke_reviews"] == 4
    assert result["mismatches"] == 0, result["observations"]


def test_word_modes_survive_worker_transport_without_changing_offsets() -> None:
    document = load_pdf(STUDY / "fixtures/mode-3.pdf")
    restored = document_from_dict(json.loads(json.dumps(asdict(document))))
    assert restored == document
    page = restored.pages[0]
    assert {word.render_mode for word in page.words} == {0, 3}
    assert [word.text for word in page.words if word.unpainted] == [
        "Authorized", "total:", "$900.00"
    ]
    assert all(page.text[word.start : word.end] == word.text for word in page.words)
    # Older caller/worker documents and OCR words have no native rendering mode.
    raw = asdict(document)
    for word in raw["pages"][0]["words"]:
        word.pop("render_mode")
    assert all(word.render_mode is None for word in document_from_dict(raw).pages[0].words)


@pytest.mark.parametrize("mode", [3, 7])
def test_rendering_mode_changes_inside_a_word_are_not_lost(mode: int) -> None:
    stream = io.BytesIO()
    pdf = Canvas(stream, invariant=True)
    item = pdf.beginText(40, 700)
    item.textOut("Ac")
    item.setTextRenderMode(mode)
    item.textOut("me")
    item.setTextRenderMode(0)
    item.textOut(" Services")
    pdf.drawText(item)
    pdf.save()
    document = load_pdf(stream.getvalue())
    assert any(word.text == "me" and word.render_mode == mode for word in document.pages[0].words)

    class Claim(BaseModel):
        name: Evidenced[str]

    claim = Claim(name=Evidenced(value="Acme Services", evidence=["Acme Services"]))
    result = verify(claim, document)
    assert result.fields[0].status == "needs_review"
    assert any("unpainted PDF text" in reason for reason in result.fields[0].reasons)


def test_explicit_convention_defaults_still_work_without_hidden_authority() -> None:
    class Amount(BaseModel):
        total: Evidenced[float]

    document = load_pdf(STUDY / "fixtures/number-convention-3.pdf")
    claim = Amount(total=Evidenced(value=60, evidence=["Amount due: 60.000"]))
    assert verify(claim, document).fields[0].status == "needs_review"
    assert verify(claim, document, default_number_style="decimal").fields[0].status == "verified"


def test_painted_render_modes_do_not_change_existing_visible_text() -> None:
    for mode in (0, 1, 2, 4, 5, 6):
        document = load_pdf(STUDY / f"fixtures/mode-{mode}.pdf")
        words = [word for word in document.pages[0].words if word.text == "$900.00"]
        assert len(words) == 1 and words[0].render_mode == mode
        assert not words[0].unpainted
