"""Actual overpainted PDFs must not borrow the replacement text's pixels."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import asdict
from pathlib import Path

import pytest
from pydantic import BaseModel

from fieldproof.document.loader import load_pdf
from fieldproof.document.model import document_from_dict
from fieldproof.schemas import Evidenced
from fieldproof.verify import verify

STUDY = Path(__file__).parents[1] / "studies/overlapping-text"


class Amount(BaseModel):
    total: Evidenced[float]


def test_replacements_rotations_crop_and_forms_against_the_authored_expected_claims() -> None:
    spec = importlib.util.spec_from_file_location("overlap_replay", STUDY / "replay.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.replay()
    assert result["cases"] == 14
    assert result["mismatches"] == 0, result["observations"]
    assert all(row["wireIdentical"] for row in result["observations"])
    assert all(
        any("overlapping native text" in reason for reason in row["field"]["reasons"])
        for row in result["observations"] if row["expected"] == "needs_review"
    )


def test_one_covered_digit_marks_the_original_word_and_survives_worker_transport() -> None:
    document = load_pdf(STUDY / "fixtures/replacement-15.pdf")
    wire = json.loads(json.dumps(asdict(document)))
    assert document_from_dict(wire) == document
    word = next(w for w in document.pages[0].words if w.text == "$900.00")
    assert word.raster_state == "ambiguous_overlap"
    assert word.paint_requires_review and not word.unpainted and not word.clip_risk
    assert document.pages[0].text[word.start:word.end] == "$900.00"


@pytest.mark.parametrize("budget", ["MAX_OVERLAP_GLYPHS", "MAX_OVERLAP_PIXELS"])
def test_incomplete_overlap_observation_cannot_become_a_verified_claim(monkeypatch, budget) -> None:
    from fieldproof.document import raster_paint

    monkeypatch.setattr(raster_paint, budget, 1)
    document = load_pdf(STUDY / "fixtures/visible-original.pdf")
    assert all(w.raster_state == "unavailable" for w in document.pages[0].words)
    result = verify(
        Amount(total=Evidenced(value=900, evidence=["Authorized total: $900.00"])), document
    ).fields[0]
    assert result.status == "needs_review"
    assert any("without a completed" in reason for reason in result.reasons)


def test_ordinary_tight_tracking_still_has_exclusive_paint() -> None:
    document = load_pdf(STUDY / "fixtures/visible-kerning.pdf")
    assert "AVATAR WATER" in document.full_text()
    assert all(w.raster_state == "contributes" for w in document.pages[0].words)
