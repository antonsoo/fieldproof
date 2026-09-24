from __future__ import annotations

from pathlib import Path

from fieldproof.document.loader import load_pdf
from fieldproof.ground.align import (
    find_candidates,
    find_quote,
    ground_quote,
    nearest_candidate,
    rects_for_match,
)
from fieldproof.ground.normalize import normalize, normalize_with_map

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def test_normalize_straightens_curly_quotes_and_collapses_whitespace() -> None:
    text = "“Hello’s   world”\t\ttest"
    assert normalize(text) == '"Hello\'s world" test'


def test_normalize_with_map_round_trips_offsets() -> None:
    text = "  Invoice   Total  "
    normalized, index_map = normalize_with_map(text)
    assert normalized == "Invoice Total"
    assert len(normalized) == len(index_map)
    # Every mapped index should point back to the matching character (once
    # whitespace has collapsed to the single space it's paired with).
    for i, ch in enumerate(normalized):
        if ch != " ":
            assert text[index_map[i]] == ch


def test_find_quote_exact_match(simple_invoice_pdf_bytes: bytes) -> None:
    doc = load_pdf(simple_invoice_pdf_bytes)
    match = find_quote("Invoice Number: INV-1001", doc.pages[0])
    assert match is not None
    assert match.is_exact
    assert match.matched_text == "Invoice Number: INV-1001"


def test_find_quote_fuzzy_match_tolerates_small_differences(
    simple_invoice_pdf_bytes: bytes,
) -> None:
    doc = load_pdf(simple_invoice_pdf_bytes)
    # Curly apostrophe + a dropped colon - not byte-identical, but a human
    # would call this the same quote.
    match = find_quote("Invoice Number INV-1001", doc.pages[0])
    assert match is not None
    assert not match.is_exact
    assert match.score >= 85


def test_find_quote_not_found_returns_none(simple_invoice_pdf_bytes: bytes) -> None:
    doc = load_pdf(simple_invoice_pdf_bytes)
    match = find_quote("a completely unrelated sentence about kangaroos", doc.pages[0])
    assert match is None


def test_find_quote_multi_line_reading_order(simple_invoice_pdf_bytes: bytes) -> None:
    doc = load_pdf(simple_invoice_pdf_bytes)
    # Spans two separate drawString lines in the source PDF; our flattened
    # page text joins them in reading order with a single space.
    match = find_quote("Issue Date: January 1, 2026 Due Date: January 31, 2026", doc.pages[0])
    assert match is not None
    assert match.score >= 95


def test_ground_quote_hyphenated_word_break(hyphenated_pdf_bytes: bytes) -> None:
    doc = load_pdf(hyphenated_pdf_bytes)
    match = ground_quote("reimbursement of travel expenses", doc)
    assert match is not None
    assert match.score >= 80


def test_ground_quote_multi_page_finds_correct_page(two_page_pdf_bytes: bytes) -> None:
    doc = load_pdf(two_page_pdf_bytes)
    match = ground_quote("$4,250.00", doc)
    assert match is not None
    assert match.page_number == 2


def test_ground_quote_prefers_hinted_page_on_tie(two_page_pdf_bytes: bytes) -> None:
    doc = load_pdf(two_page_pdf_bytes)
    match = ground_quote("Contoso Ltd", doc, hint_page=1)
    assert match is not None
    assert match.page_number == 1


def test_rects_for_match_groups_single_line_into_one_rect(simple_invoice_pdf_bytes: bytes) -> None:
    doc = load_pdf(simple_invoice_pdf_bytes)
    match = find_quote("Invoice Number: INV-1001", doc.pages[0])
    assert match is not None
    rects = rects_for_match(match)
    assert len(rects) == 1


def test_rects_for_match_multi_line_quote_produces_multiple_rects(
    simple_invoice_pdf_bytes: bytes,
) -> None:
    doc = load_pdf(simple_invoice_pdf_bytes)
    match = find_quote("Issue Date: January 1, 2026 Due Date: January 31, 2026", doc.pages[0])
    assert match is not None
    rects = rects_for_match(match)
    assert len(rects) == 2


# --- word-boundary alignment and ambiguity (regression: "1" inside "4821") ---
#
# examples/invoice.pdf's letterhead has the street address "4821 Harbor
# Industrial Way", and its line items table has two rows with quantity 1
# ("Fuel surcharge" and "Warehouse handling fee"). A short quote like "1"
# must never match the trailing digit of "4821" - only whole word tokens -
# and when it legitimately occurs more than once, every occurrence must be
# reported rather than silently picking whichever comes first.


def test_word_aligned_match_never_lands_inside_a_longer_number() -> None:
    doc = load_pdf(EXAMPLES_DIR / "invoice.pdf")
    page = doc.pages[0]

    candidates = find_candidates("1", page)

    assert candidates, "expected the standalone '1' quantities to be found"
    for match in candidates:
        assert match.matched_text == "1"
        assert "4821" not in (w.text for w in match.words)


def test_find_candidates_reports_every_ambiguous_occurrence() -> None:
    doc = load_pdf(EXAMPLES_DIR / "invoice.pdf")
    page = doc.pages[0]

    candidates = find_candidates("1", page)

    # Exactly the two "quantity 1" line items ("Fuel surcharge", "Warehouse
    # handling fee") - not the "1" inside "4821", "1,740.00" or "$2,458.00"
    # etc, since none of those have "1" as a standalone word token.
    assert len(candidates) == 2
    tops = sorted(m.top for m in candidates)
    assert tops[1] - tops[0] > 5  # two distinct rows, not the same line twice


def test_nearest_candidate_picks_the_occurrence_closest_to_the_hint() -> None:
    doc = load_pdf(EXAMPLES_DIR / "invoice.pdf")
    page = doc.pages[0]

    candidates = find_candidates("1", page)
    assert len(candidates) == 2
    first_row, second_row = sorted(candidates, key=lambda m: m.top)

    # A hint anchored on the first row's vertical position should resolve
    # to that row's "1", not the other one.
    hint = find_quote("Fuel surcharge", page)
    assert hint is not None
    resolved = nearest_candidate(candidates, hint)
    assert resolved.top == first_row.top
    assert resolved is not second_row
