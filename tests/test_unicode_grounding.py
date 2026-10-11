"""Case-only evidence keeps every original source occurrence through Unicode expansion."""

import json
from pathlib import Path

import pytest

from fieldproof.document.loader import load_pdf
from fieldproof.ground.align import find_candidates_in_document
from fieldproof.schemas.receipt import Receipt
from fieldproof.verify.engine import verify

STUDY = Path(__file__).parents[1] / "studies/unicode-grounding"
CASES = json.loads((STUDY / "cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_unicode_case_evidence_through_actual_pdf(case: dict) -> None:
    path = STUDY / "fixtures" / case["id"]
    document = load_pdf(path.with_suffix(".pdf"))
    data = Receipt.model_validate_json(path.with_suffix(".json").read_bytes())
    candidates = find_candidates_in_document(
        case["quote"], document, hint_page=case.get("hint_page", 1)
    )
    assert len(candidates) == case["candidates"]
    result = verify(data, document).fields[0]
    assert result.status.value == case["expect"]
    if len(candidates) > 1:
        assert result.rects == [] and result.page is None
        assert any("ambiguous" in reason for reason in result.reasons)
    if len(candidates) == 1:
        match = candidates[0]
        page = document.page(match.page_number)
        assert page.text[match.start : match.end] == match.matched_text
        assert match.matched_text in case["pages"][match.page_number - 1]
        assert result.rects == [word.bbox.to_dict() for word in match.words]
        assert result.matched_text == match.matched_text
    if case["id"] == "page-hint-duplicates":
        assert [match.page_number for match in candidates] == [2, 1]
    if case["id"] == "complete-expanded-word":
        assert candidates[0].matched_text == "Straße"
    if case["id"] == "fuzzy-after-expansion":
        assert result.matched_text == "NORTHWIND"
        assert not candidates[0].is_strong
