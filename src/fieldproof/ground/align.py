"""Locate a quoted string on a page: exact match first, fuzzy fallback.

This is the core of "showing its work": a field's evidence is worthless if
we can't point at where on the page it actually is. `ground_quote` tries an
exact (normalized) substring match first, since that's unambiguous and
free, and only falls back to rapidfuzz's partial-ratio alignment - which
finds the best-scoring substring of the page text for a shorter query - when
the model's transcription doesn't match byte-for-byte (OCR noise, a
retyped/paraphrased quote, minor whitespace differences).
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from fieldproof.document.model import BBox, Document, Page, Word
from fieldproof.ground.normalize import normalize, normalize_with_map

#: Below this fuzzy score (0-100), we consider the quote not found on the
#: page rather than report a misleading low-confidence match.
MIN_MATCH_SCORE = 70.0

#: At or above this score, a match is "strong" evidence; below it (but
#: above MIN_MATCH_SCORE) it's "weak" - used by fieldproof.verify to decide
#: needs_review vs. verified.
STRONG_MATCH_SCORE = 92.0


@dataclass(frozen=True, slots=True)
class GroundingMatch:
    """Where a quote was found: its span in `Page.text`, the words it
    covers, and how good the match was (100 = exact)."""

    quote: str
    page_number: int
    start: int
    end: int
    score: float
    matched_text: str
    words: tuple[Word, ...]

    @property
    def is_exact(self) -> bool:
        return self.score >= 100.0

    @property
    def is_strong(self) -> bool:
        return self.score >= STRONG_MATCH_SCORE


def find_quote(quote: str, page: Page) -> GroundingMatch | None:
    """Find `quote` on a single page, or return None if it isn't there."""
    normalized_quote = normalize(quote)
    if not normalized_quote or not page.words:
        return None

    norm_page_text, index_map = normalize_with_map(page.text)
    if not norm_page_text:
        return None

    exact_idx = norm_page_text.find(normalized_quote)
    if exact_idx != -1:
        norm_start, norm_end = exact_idx, exact_idx + len(normalized_quote)
        score = 100.0
    else:
        alignment = fuzz.partial_ratio_alignment(normalized_quote, norm_page_text)
        if alignment is None or alignment.dest_end <= alignment.dest_start:
            return None
        if alignment.score < MIN_MATCH_SCORE:
            return None
        norm_start, norm_end = alignment.dest_start, alignment.dest_end
        score = alignment.score

    start = index_map[norm_start]
    end = index_map[norm_end - 1] + 1
    words = _words_overlapping(page.words, start, end)
    if not words:
        return None

    return GroundingMatch(
        quote=quote,
        page_number=page.number,
        start=start,
        end=end,
        score=score,
        matched_text=page.text[start:end],
        words=tuple(words),
    )


def ground_quote(
    quote: str, document: Document, *, hint_page: int | None = None
) -> GroundingMatch | None:
    """Find `quote` anywhere in `document`, preferring `hint_page` (the page
    the extractor claimed) when scores tie, and returning the best-scoring
    match across all pages otherwise - a provider's page number is often
    right but not authoritative."""
    best: GroundingMatch | None = None
    pages = sorted(document.pages, key=lambda p: p.number != hint_page)
    for page in pages:
        match = find_quote(quote, page)
        if match is None:
            continue
        if best is None or match.score > best.score:
            best = match
        if best is not None and best.is_exact and page.number == hint_page:
            break
    return best


def _words_overlapping(words: list[Word], start: int, end: int) -> list[Word]:
    return [w for w in words if w.start < end and w.end > start]


def rects_for_match(match: GroundingMatch, line_tolerance: float = 3.0) -> list[BBox]:
    """Merge a match's words into one highlight rectangle per line, so a
    quote spanning several lines renders as several boxes instead of one box
    covering the full width between the first and last line."""
    if not match.words:
        return []
    ordered = sorted(match.words, key=lambda w: (w.bbox.top, w.bbox.x0))
    rects: list[BBox] = []
    current = ordered[0].bbox
    current_top = ordered[0].bbox.top
    for w in ordered[1:]:
        if abs(w.bbox.top - current_top) <= line_tolerance:
            current = current.union(w.bbox)
        else:
            rects.append(current)
            current = w.bbox
            current_top = w.bbox.top
    rects.append(current)
    return rects
