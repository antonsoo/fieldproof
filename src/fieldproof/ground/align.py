"""Locate a quoted string on a page: exact match first, fuzzy fallback.

This is the core of "showing its work": a field's evidence is worthless if
we can't point at where on the page it actually is - and worse than
worthless if it points at the *wrong* place while still reporting
"verified". A short quote like "1" must never be allowed to match the
trailing digit of a street address like "4821": every exact match is
required to land on whole word boundaries (`_word_aligned_occurrences`),
and when a quote genuinely occurs more than once, `find_candidates` returns
every occurrence rather than silently picking the first one, so a caller
(`fieldproof.verify.engine`) can disambiguate by context or admit it can't.
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

    @property
    def top(self) -> float:
        """Vertical position (PDF points from the page top) used to judge
        which of several ambiguous matches is "on the same row" as another
        field's evidence - the average of its words' tops, so a match is
        represented by a single comparable y-coordinate."""
        if not self.words:
            return 0.0
        return sum(w.bbox.top for w in self.words) / len(self.words)


def _word_aligned_occurrences(quote: str, page: Page) -> list[GroundingMatch]:
    """Every exact (normalized) occurrence of `quote` in `page` whose span
    starts and ends on a whole word boundary - i.e. never starts or ends
    mid-token. Without this check, a one-character quote like "1" would
    happily match the trailing digit of "4821"; pdfplumber never splits
    "4821" into separate word tokens, so requiring both the match's start
    and its end to coincide with some word's start/end offset rules that
    out entirely, while still allowing a quote that spans several whole
    words (e.g. a full line-item row)."""
    normalized_quote = normalize(quote)
    if not normalized_quote or not page.words:
        return []

    norm_page_text, index_map = normalize_with_map(page.text)
    if not norm_page_text:
        return []

    word_starts = {w.start for w in page.words}
    word_ends = {w.end for w in page.words}

    matches: list[GroundingMatch] = []
    qlen = len(normalized_quote)
    search_from = 0
    while True:
        idx = norm_page_text.find(normalized_quote, search_from)
        if idx == -1:
            break
        search_from = idx + 1

        start = index_map[idx]
        end = index_map[idx + qlen - 1] + 1
        if start not in word_starts or end not in word_ends:
            continue

        words = _words_overlapping(page.words, start, end)
        if not words:
            continue
        matches.append(
            GroundingMatch(
                quote=quote,
                page_number=page.number,
                start=start,
                end=end,
                score=100.0,
                matched_text=page.text[start:end],
                words=tuple(words),
            )
        )
    return matches


def _fuzzy_match(quote: str, page: Page) -> GroundingMatch | None:
    normalized_quote = normalize(quote)
    if not normalized_quote or not page.words:
        return None

    norm_page_text, index_map = normalize_with_map(page.text)
    if not norm_page_text:
        return None

    alignment = fuzz.partial_ratio_alignment(normalized_quote, norm_page_text)
    if alignment is None or alignment.dest_end <= alignment.dest_start:
        return None
    if alignment.score < MIN_MATCH_SCORE:
        return None

    start = index_map[alignment.dest_start]
    end = index_map[alignment.dest_end - 1] + 1
    words = _words_overlapping(page.words, start, end)
    if not words:
        return None

    return GroundingMatch(
        quote=quote,
        page_number=page.number,
        start=start,
        end=end,
        score=alignment.score,
        matched_text=page.text[start:end],
        words=tuple(words),
    )


def find_candidates(quote: str, page: Page) -> list[GroundingMatch]:
    """All plausible locations for `quote` on `page`: every word-aligned
    exact occurrence if there is at least one, otherwise the single best
    fuzzy match (fuzzy scoring across many candidates isn't meaningful, so
    fuzzy only ever contributes one). An empty list means not found."""
    exact = _word_aligned_occurrences(quote, page)
    if exact:
        return exact
    fuzzy = _fuzzy_match(quote, page)
    return [fuzzy] if fuzzy is not None else []


def find_quote(quote: str, page: Page) -> GroundingMatch | None:
    """Find `quote` on a single page, or return None if it isn't there.

    A low-level convenience for simple/unambiguous lookups: if `quote`
    occurs more than once, this returns the first occurrence without
    trying to disambiguate - callers that need to handle ambiguity
    correctly (as `fieldproof.verify.engine` does) should use
    `find_candidates` directly instead.
    """
    candidates = find_candidates(quote, page)
    return candidates[0] if candidates else None


def ground_quote(
    quote: str, document: Document, *, hint_page: int | None = None
) -> GroundingMatch | None:
    """Find `quote` anywhere in `document`, preferring `hint_page` (the page
    the extractor claimed) when scores tie, and returning the best-scoring
    match across all pages otherwise - a provider's page number is often
    right but not authoritative. Like `find_quote`, does not disambiguate
    multiple occurrences - see `find_candidates_in_document`."""
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


def find_candidates_in_document(
    quote: str, document: Document, *, hint_page: int | None = None
) -> list[GroundingMatch]:
    """Every plausible location for `quote` anywhere in `document`. If any
    page has word-aligned exact occurrences, only exact occurrences (from
    all pages, `hint_page` first) are returned - fuzzy matches from other
    pages are never mixed in as "maybe this instead" once an exact hit
    exists anywhere. If none do, falls back to the single best fuzzy match
    across pages."""
    pages = sorted(document.pages, key=lambda p: p.number != hint_page)

    exact: list[GroundingMatch] = []
    for page in pages:
        exact.extend(_word_aligned_occurrences(quote, page))
    if exact:
        return exact

    best_fuzzy: GroundingMatch | None = None
    for page in pages:
        match = _fuzzy_match(quote, page)
        if match is not None and (best_fuzzy is None or match.score > best_fuzzy.score):
            best_fuzzy = match
    return [best_fuzzy] if best_fuzzy is not None else []


def nearest_candidate(candidates: list[GroundingMatch], hint: GroundingMatch) -> GroundingMatch:
    """Pick whichever of several ambiguous `candidates` is closest to
    `hint` - same page first, then smallest vertical distance between
    their word tops. Used to resolve "the quote appears N times" by
    preferring the occurrence on the same row as another field from the
    same object that's already been grounded (e.g. a line item's
    description) - see `fieldproof.verify.engine`."""

    def distance(candidate: GroundingMatch) -> tuple[int, float]:
        same_page = 0 if candidate.page_number == hint.page_number else 1
        return (same_page, abs(candidate.top - hint.top))

    return min(candidates, key=distance)


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
