"""Renderer geometry must not lend a different glyph's overhang to covered text."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pdfplumber
import pytest
from pydantic import BaseModel
from pypdfium2 import raw

from fieldproof.document.loader import load_pdf
from fieldproof.document.text_modes import ModePage
from fieldproof.schemas import Evidenced
from fieldproof.verify import verify

STUDY = Path(__file__).resolve().parents[1] / "studies/native-glyph-bounds"


class Amount(BaseModel):
    total: Evidenced[float]


def test_authored_font_overhangs_and_visible_controls_after_worker_transport() -> None:
    spec = importlib.util.spec_from_file_location("native_bounds_replay", STUDY / "replay.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.replay()
    assert result["cases"] == 36 and result["mismatches"] == 0, result["observations"]
    hidden = [row for row in result["observations"] if row["hidden"]]
    assert len(hidden) == 25 and all(row["field"]["status"] == "needs_review" for row in hidden)
    visible = [row for row in result["observations"] if not row["hidden"]]
    assert sum(row["field"]["status"] == "verified" for row in visible) == 9
    nearby = next(row for row in visible if row["case"] == "nearby-miter-stroke")
    assert nearby["field"]["status"] == "needs_review"
    far = next(row for row in visible if row["case"] == "far-miter-stroke")
    assert far["field"]["status"] == "verified"
    unsupported = next(row for row in visible if row["case"] == "unreadable-miter-limit")
    assert unsupported["field"]["status"] == "needs_review"
    assert all(w["raster_state"] == "unavailable" for w in unsupported["quoted_words"])


@pytest.mark.parametrize(
    ("case", "bound"),
    [
        ("visible-plain", 10),
        ("larger-miter-limit", 30),
        ("unreadable-miter-limit", None),
    ],
)
def test_page_miter_bound_includes_form_extgstate_and_retains_unknowns(case, bound) -> None:
    with pdfplumber.open(STUDY / "fixtures" / f"{case}.pdf") as pdf:
        original = pdf.pages[0]
        page = ModePage(pdf, original.page_obj, original.page_number, original.initial_doctop)
        try:
            assert page.miter_limit_bound == bound
        finally:
            page.close()


@pytest.mark.parametrize("failure", ["missing-api", "failed-bounds", "different-unicode"])
def test_incomplete_or_mismatched_native_geometry_cannot_certify_the_source(
    monkeypatch, failure
) -> None:
    if failure == "missing-api":
        monkeypatch.delattr(raw, "FPDFText_GetTextObject")
    elif failure == "failed-bounds":
        monkeypatch.setattr(raw, "FPDFText_GetLooseCharBox", lambda *args: 0)
    else:
        monkeypatch.setattr(raw, "FPDFText_GetUnicode", lambda *args: ord("X"))
    document = load_pdf(STUDY / "fixtures/visible-plain.pdf")
    assert document.full_text() and document.pages[0].words
    assert all(w.raster_state == "unavailable" for p in document.pages for w in p.words)
    data = Amount(total=Evidenced(value=900, evidence=["Authorized total: $900.00"]))
    assert verify(data, document).fields[0].status == "needs_review"
