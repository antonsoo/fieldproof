"""Prepared evidence must preserve ambiguity and never reuse another review's geometry."""

from __future__ import annotations

from dataclasses import replace

from pydantic import BaseModel

from fieldproof.document.model import BBox, Document, Page, Word
from fieldproof.ground.align import GroundingIndex, find_candidates
from fieldproof.schemas import Evidenced
from fieldproof.verify.engine import FieldStatus, verify
from fieldproof.verify.rows import RowEvidenceRule


def page(lines: list[str], number: int = 1) -> Page:
    text = " ".join(lines)
    offset = 0
    words = []
    for row, line in enumerate(lines):
        for token in line.split():
            words.append(
                Word(
                    token,
                    BBox(offset, row * 20, offset + len(token), row * 20 + 10),
                    offset,
                    offset + len(token),
                )
            )
            offset += len(token) + 1
    return Page(number, 600, 800, text, words)


def test_reused_candidates_keep_numeric_omissions_ambiguous_and_page_hints_non_authoritative():
    document = Document("repeated.pdf", [page(["Tax 6%", "Count 6"]), page(["Other 6"], 2)])
    index = GroundingIndex(document)
    for hint in (1, 2, 1, None, 9, 2):
        candidates = index.candidates("6", hint_page=hint)
        expected = [(1, "6%", False), (1, "6", True), (2, "6", True)]
        if hint == 2:
            expected = [expected[2], *expected[:2]]
        assert [(m.page_number, m.matched_text, m.is_strong) for m in candidates] == expected
        # Consumers can reorder or clear a result without corrupting another field.
        candidates.clear()
        assert len(index.candidates("6", hint_page=hint)) == 3


def test_candidate_eviction_and_oversized_results_preserve_every_occurrence(monkeypatch):
    monkeypatch.setattr(GroundingIndex, "MAX_QUOTES", 2)
    monkeypatch.setattr(GroundingIndex, "MAX_REFERENCES", 3)
    index = GroundingIndex(Document("small-cache.pdf", [page(["Alpha 6% 6 6 Beta Gamma"])]))
    for quote in ("6", "alpha", "Beta", "Gamma", "6", "alpha", "6"):
        actual = index.candidates(quote)
        if quote == "6":
            assert [(m.matched_text, m.is_strong) for m in actual] == [
                ("6%", False),
                ("6", True),
                ("6", True),
            ]
        else:
            assert len(actual) == 1 and actual[0].matched_text == quote.capitalize()


def test_shared_quote_does_not_share_the_field_value_verdict():
    class Claims(BaseModel):
        correct: Evidenced[float]
        incorrect: Evidenced[float]

    data = Claims(
        correct=Evidenced(value=12, evidence=["12.00"]),
        incorrect=Evidenced(value=12000, evidence=["12.00"]),
    )
    result = verify(data, Document("amount.pdf", [page(["Total 12.00"])]))
    assert [field.status for field in result.fields] == [
        FieldStatus.VERIFIED,
        FieldStatus.NEEDS_REVIEW,
    ]
    assert result.fields[0].rects == result.fields[1].rects


def test_new_verification_reads_changed_geometry_and_another_document():
    class Item(BaseModel):
        description: Evidenced[str]
        amount: Evidenced[float]

    class Table(BaseModel):
        items: list[Item]

    data = Table(
        items=[
            Item(
                description=Evidenced(value="Alpha", evidence=["Alpha"]),
                amount=Evidenced(value=1, evidence=["1"]),
            )
        ]
    )
    document = Document("invoice.pdf", [page(["Alpha", "1"])])
    rules = [RowEvidenceRule("items", "description", ("amount",))]
    before = verify(data, document, row_rules=rules)
    assert before.row_checks[0].status == "separate"
    assert before.fields[1].status is FieldStatus.NEEDS_REVIEW
    old = document.pages[0].words[1]
    document.pages[0].words[1] = replace(old, bbox=BBox(60, 0, 65, 10))
    after = verify(data, document, row_rules=rules)
    assert after.row_checks[0].status == "same_line"
    assert after.fields[1].status is FieldStatus.VERIFIED
    assert after.fields[1].rects == [{"x0": 60, "top": 0, "x1": 65, "bottom": 10}]
    # Same source label and page number, but its signed amount disagrees.
    other = verify(data, Document("invoice.pdf", [page(["Alpha -1"])]), row_rules=rules)
    assert other.fields[1].status is FieldStatus.NEEDS_REVIEW
    assert other.fields[1].matched_text == "-1"


def test_nonmonotonic_library_word_lists_keep_original_membership():
    source = page(["Alpha Beta"])
    source.words.reverse()
    (match,) = find_candidates("Alpha Beta", source)
    assert match.is_strong and match.matched_text == "Alpha Beta"
    assert [word.text for word in match.words] == ["Beta", "Alpha"]
