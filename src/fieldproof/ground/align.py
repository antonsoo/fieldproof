"""Locate a quoted string on a page: exact match first, fuzzy fallback.

This is the core of "showing its work": a field's evidence is worthless if
we can't point at where on the page it actually is - and worse than
worthless if it points at the *wrong* place while still reporting
"verified". A short quote like "1" must never be allowed to match the
trailing digit of a street address like "4821": every exact match is
required to cover whole words (`_word_aligned_occurrences`; punctuation
attached to a word, like the comma in "1," or the "$" in "$2,458.00", may be
left out, letters and digits may not), and a fuzzy match that cuts a word is
scored against the whole words it touches (`_fuzzy_match`), so "wind" does
not count as found in "Northwind". When a quote genuinely occurs more than
once, `find_candidates` returns every occurrence rather than silently
picking the first one, so a caller (`fieldproof.verify.engine`) can
disambiguate by context or admit it can't.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import OrderedDict
from dataclasses import dataclass, replace
from functools import cached_property
from math import isfinite

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from fieldproof.document.model import BBox, Document, Page, Word
from fieldproof.ground.lines import separate_numeric_regions
from fieldproof.ground.normalize import normalize, normalize_with_map
from fieldproof.ground.values import (
    NumberToken,
    amount_readings,
    dates_in,
    number_tokens,
    whole_date,
)

#: Below this fuzzy score (0-100), we consider the quote not found on the
#: page rather than report a misleading low-confidence match.
MIN_MATCH_SCORE = 70.0

#: At or above this score, a match is "strong" evidence; below it (but
#: above MIN_MATCH_SCORE) it's "weak" - used by fieldproof.verify to decide
#: needs_review vs. verified.
STRONG_MATCH_SCORE = 92.0


#: Score of a match that is exact except for letter case: not 100, which means the page has
#: the quote's characters, but a strong match.
CASE_ONLY_SCORE = 99.0


@dataclass(frozen=True, slots=True)
class GroundingMatch:
    """Where a quote was found: its span in `Page.text`, the words it
    covers, and how good the match was (100 = exact).

    `letters_agree` says whether the quote and the words it was found at have the same
    letters, digits and numeric signs/units in the same order, ignoring case, spacing
    and other punctuation (None: not
    judged, so only `score` speaks). A fuzzy match can score 97/100 with one letter
    different, which is how a misquoted name looks, so it is not strong evidence; a fuzzy
    match that differs only in case, spacing or punctuation is, whatever its score.

    `by_value` marks a match found by reading both the quote and the page as numbers or
    dates and finding the same value ("60000" at "60.000", "2018-12-25" at "25/12/2018"),
    not by comparing characters."""

    quote: str
    page_number: int
    start: int
    end: int
    score: float
    matched_text: str
    words: tuple[Word, ...]
    letters_agree: bool | None = None
    by_value: bool = False

    @property
    def is_exact(self) -> bool:
        return self.score >= 100.0 and not self.by_value

    @property
    def is_strong(self) -> bool:
        if self.letters_agree is None:
            return self.score >= STRONG_MATCH_SCORE
        return self.letters_agree

    @property
    def top(self) -> float:
        """Vertical position (PDF points from the page top) used to judge
        which of several ambiguous matches is "on the same row" as another
        field's evidence - the average of its words' tops, so a match is
        represented by a single comparable y-coordinate."""
        if not self.words:
            return 0.0
        return sum(w.bbox.top for w in self.words) / len(self.words)


class _PageIndex:
    """One verification's text/geometry snapshot, prepared once per page."""

    def __init__(self, page: Page) -> None:
        self.page = replace(page, words=list(page.words))
        self.normalized, self.offsets = normalize_with_map(page.text)
        self.numbers = number_tokens(separate_numeric_regions(page.text, self.page.words))
        self.number_starts = [token.start for token in self.numbers]
        self.number_ends = [token.end for token in self.numbers]
        self.word_starts = [word.start for word in self.page.words]
        self.word_ends = [word.end for word in self.page.words]
        # Loader words are ordered by text offset. Library callers can supply
        # unusual word lists; preserve their original ordering and membership.
        self.ordered_words = (
            self.word_starts == sorted(self.word_starts)
            and self.word_ends == sorted(self.word_ends)
            and all(word.start < word.end for word in self.page.words)
        )

    @cached_property
    def casefolded(self) -> tuple[str, list[int]]:
        # Case folding can expand one source character (e.g. İ or ß). Map every
        # output character back to that source offset so later text stays aligned,
        # and _splits_a_character can reject half of an expanded character.
        offsets = [
            offset
            for ch, offset in zip(self.normalized, self.offsets, strict=True)
            for _ in ch.casefold()
        ]
        return self.normalized.casefold(), offsets

    def words_overlapping(self, start: int, end: int) -> list[Word]:
        if not self.ordered_words:
            return [w for w in self.page.words if w.start < end and w.end > start]
        first = bisect_right(self.word_ends, start)
        last = bisect_left(self.word_starts, end)
        return self.page.words[first:last]

    def numbers_overlapping(self, start: int, end: int) -> tuple[NumberToken, ...]:
        first = bisect_right(self.number_ends, start)
        last = bisect_left(self.number_starts, end)
        return self.numbers[first:last]


def _covers_whole_words(
    index: _PageIndex, start: int, end: int, words: list[Word], *, numeric_modifiers: bool = True
) -> bool:
    """Does the span `[start, end)` cover every letter and digit of the words
    it touches? Punctuation glued to a word may be left outside: the page's
    words are split on whitespace, so "1," and "$2,458.00" are one word each,
    and a quote of "1" or "2,458.00" still names the whole of what is there.
    "458.00" does not: the "2," it leaves out is part of the number."""
    page = index.page
    before = page.text[words[0].start : start]
    left_out = before + page.text[end : words[-1].end]
    if any(ch.isalnum() for ch in left_out):
        return False
    if not numeric_modifiers:
        return True
    # Currency can be omitted, but a sign, accounting bracket or percentage cannot.
    # Include adjacent words too: "- $100" is one signed amount, not a positive
    # number because a model quoted only the word with the currency symbol.
    for token in index.numbers_overlapping(start, end):
        if token.start < end and token.end > start and (token.start < start or token.end > end):
            fragment_text = page.text[max(start, token.start) : min(end, token.end)]
            if not any(ch.isdecimal() for ch in fragment_text):
                continue  # A quote of the label/sign alone makes no numeric claim.
            original = token.readings()
            fragment = amount_readings(fragment_text)
            if not original or {r.value for r in original} != {r.value for r in fragment}:
                return False
    return True


def _whole_numeric_span(index: _PageIndex, start: int, end: int) -> tuple[int, int]:
    """Expand an incomplete quote to the entire numeric token it touches."""
    for token in index.numbers:
        if token.start < end and token.end > start:
            start, end = min(start, token.start), max(end, token.end)
    return start, end


def _splits_a_character(index_map: list[int], first: int, last: int) -> bool:
    """One page character can normalize to several (the ligature "\ufb01" to
    "fi"). Does the normalized span `first..last` begin or end between them?
    Its page span would then cover a character the quote only half matches."""
    begins_inside = first > 0 and index_map[first - 1] == index_map[first]
    ends_inside = last + 1 < len(index_map) and index_map[last + 1] == index_map[last]
    return begins_inside or ends_inside


def _word_aligned_occurrences(
    quote: str, index: _PageIndex, *, fold_case: bool = False
) -> list[GroundingMatch]:
    """Every normalized occurrence of `quote` in `page` that covers whole words.
    Occurrences omitting a numeric modifier are expanded and marked weak so they
    remain visible to ambiguity checking. Without word boundaries, a
    one-character quote like "1" would happily match the trailing digit of
    "4821"; pdfplumber never splits "4821" into separate word tokens, so
    requiring the match to leave no letter or digit of a touched word
    uncovered rules that out entirely, while still allowing a quote that
    spans several whole words (e.g. a full line-item row)."""
    page = index.page
    normalized_quote = normalize(quote)
    if not normalized_quote or not page.words:
        return []

    norm_page_text, index_map = index.normalized, index.offsets
    if not norm_page_text:
        return []
    if fold_case:
        # A quote that differs from the page only in case is found at every place the
        # page has it, just as an exact one is, so a repeated name stays ambiguous.
        norm_page_text, index_map = index.casefolded
        normalized_quote = normalized_quote.casefold()

    matches: list[GroundingMatch] = []
    qlen = len(normalized_quote)
    search_from = 0
    while True:
        idx = norm_page_text.find(normalized_quote, search_from)
        if idx == -1:
            break
        search_from = idx + 1

        last = idx + qlen - 1
        if _splits_a_character(index_map, idx, last):
            continue

        start = index_map[idx]
        end = index_map[last] + 1
        words = index.words_overlapping(start, end)
        if not words or not _covers_whole_words(index, start, end, words, numeric_modifiers=False):
            continue
        if not _covers_whole_words(index, start, end, words):
            # Keep this occurrence as weak evidence instead of deleting it.
            # Otherwise "6" on a page with "6%" and an unrelated "6" becomes
            # uniquely verified at the unrelated place. The full token is what
            # the value check and the human review highlight must see.
            start, end = _whole_numeric_span(index, start, end)
            matched_text = page.text[start:end]
            matches.append(
                GroundingMatch(
                    quote=quote,
                    page_number=page.number,
                    start=start,
                    end=end,
                    score=fuzz.ratio(
                        normalized_quote.casefold(), normalize(matched_text).casefold()
                    ),
                    matched_text=matched_text,
                    words=tuple(index.words_overlapping(start, end)),
                    letters_agree=False,
                )
            )
            continue
        matches.append(
            GroundingMatch(
                quote=quote,
                page_number=page.number,
                start=start,
                end=end,
                score=CASE_ONLY_SCORE if fold_case else 100.0,
                letters_agree=True if fold_case else None,
                matched_text=page.text[start:end],
                words=tuple(words),
            )
        )
    return matches


def _fuzzy_match(quote: str, index: _PageIndex) -> GroundingMatch | None:
    page = index.page
    normalized_quote = normalize(quote)
    if not normalized_quote or not page.words:
        return None

    norm_page_text, index_map = index.casefolded
    if not norm_page_text:
        return None

    # Case is not what a misquote gets wrong, and a model that title-cases a name has
    # not changed what the page says; letters and digits are checked separately below.
    alignment = fuzz.partial_ratio_alignment(normalized_quote.casefold(), norm_page_text)
    if alignment is None or alignment.dest_end <= alignment.dest_start:
        return None
    if alignment.score < MIN_MATCH_SCORE:
        return None

    start = index_map[alignment.dest_start]
    end = index_map[alignment.dest_end - 1] + 1
    words = index.words_overlapping(start, end)
    if not words:
        return None

    score = alignment.score
    cut = _splits_a_character(index_map, alignment.dest_start, alignment.dest_end - 1)
    if cut or not _covers_whole_words(index, start, end, words):
        # The best window cuts a word: the quote is a fragment of something
        # longer on the page ("wind" in "Northwind", "0214" in "NW-20260214").
        # A fragment is a perfect *partial* match, which is exactly the
        # misleading 100 this module exists to refuse. Judge the quote against
        # the whole words instead.
        start, end = _whole_numeric_span(index, words[0].start, words[-1].end)
        words = index.words_overlapping(start, end)
        score = fuzz.ratio(normalized_quote.casefold(), normalize(page.text[start:end]).casefold())
        if score < MIN_MATCH_SCORE:
            return None

    matched_text = page.text[start:end]
    return GroundingMatch(
        quote=quote,
        page_number=page.number,
        start=start,
        end=end,
        score=score,
        matched_text=matched_text,
        words=tuple(words),
        letters_agree=_skeleton(quote) == _skeleton(matched_text),
    )


def _skeleton(text: str) -> str:
    """The letters and digits of `text` in order, case-folded: what is left when case,
    spacing and punctuation are ignored. A separator between two digits is kept, because
    there it is part of the number: "12.00" and "12:00" are not the same, and neither is
    "1,200". Numeric signs (including accounting parentheses) and rates are kept too."""
    folded = normalize(text).casefold()
    # Record modifiers where their amount starts. Signs before a currency symbol,
    # trailing minus signs and accounting parentheses carry the same numeric role.
    markers = {
        token.start: ("-" if token.negative else "") + ("%" if token.percent else "")
        for token in number_tokens(folded)
        if token.negative or token.percent
    }
    kept: list[str] = []
    for i, ch in enumerate(folded):
        if i in markers:
            kept.append(markers[i])
        before = folded[i - 1] if i else ""
        after = folded[i + 1 : i + 2]
        if ch.isalnum():
            kept.append(ch)
        elif ch.isspace():
            continue
        elif before.isdigit() and after.isdigit():
            kept.append(ch)
    return "".join(kept)


def letter_distance(a: str, b: str) -> int:
    """How many letters or digits must change to turn `a` into `b`, ignoring case, spacing
    and punctuation (see `_skeleton`)."""
    return Levenshtein.distance(_skeleton(a), _skeleton(b))


def _value_occurrences(quote: str, index: _PageIndex) -> list[GroundingMatch]:
    """Where `page` writes the same number or date as `quote`, however it writes it.

    Only a quote that is nothing but an amount ("60000", "$1,234.50") or nothing but a date
    ("2018-12-25", "25 December 2018") is read this way. A model that normalizes a value
    and quotes the normalized form has rewritten the page's characters; comparing the
    characters by edit distance finds "19.80" at "18.90" and misses "60000" at "60.000",
    so these are compared as values. A token with two readings ("60.000") matches on
    either; `fieldproof.verify` says which the document means."""
    page = index.page
    stripped = quote.strip()
    if not stripped or not page.words:
        return []
    found: list[tuple[int, int]] = []

    wanted = amount_readings(stripped) if len(stripped.split()) == 1 else []
    if wanted:
        for word in page.words:
            theirs = amount_readings(word.text)
            if any(a.value == b.value for a in wanted for b in theirs):
                found.append((word.start, word.end))
    else:
        days = whole_date(stripped)
        if days:
            for start, end, page_days in dates_in(page.text):
                if days & page_days:
                    found.append((start, end))

    matches: list[GroundingMatch] = []
    for start, end in found:
        words = index.words_overlapping(start, end)
        if not words or not _covers_whole_words(index, start, end, words):
            continue
        matches.append(
            GroundingMatch(
                quote=quote,
                page_number=page.number,
                start=words[0].start,
                end=words[-1].end,
                score=100.0,
                matched_text=page.text[words[0].start : words[-1].end],
                words=tuple(words),
                letters_agree=True,
                by_value=True,
            )
        )
    return matches


def find_candidates(quote: str, page: Page) -> list[GroundingMatch]:
    """All plausible locations for `quote` on `page`: every word-aligned
    occurrence (including weak numeric omissions) if there is one, otherwise every one that differs
    only in case, otherwise every place the page writes
    the same number or date as a quote that is only that (`_value_occurrences`),
    otherwise the single best fuzzy match (fuzzy scoring across many candidates isn't meaningful, so
    fuzzy only ever contributes one). An empty list means not found."""
    if not page.words or not normalize(quote):
        return []
    index = _PageIndex(page)
    exact = _word_aligned_occurrences(quote, index)
    if exact:
        return exact
    folded = _word_aligned_occurrences(quote, index, fold_case=True)
    if folded:
        return folded
    by_value = _value_occurrences(quote, index)
    if by_value:
        return by_value
    fuzzy = _fuzzy_match(quote, index)
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
    page has word-aligned occurrences, only those occurrences (from
    all pages, `hint_page` first) are returned - fuzzy matches from other
    pages are never mixed in as "maybe this instead" once an exact hit
    exists anywhere. Weak numeric omissions are retained to preserve ambiguity.
    If none do, a quote that is only a number or a date is
    looked for by value (`_value_occurrences`); anything else falls back to the
    single best fuzzy match across pages."""
    return GroundingIndex(document).candidates(quote, hint_page=hint_page)


class GroundingIndex:
    """Reuse a document snapshot only within one verification operation.

    Candidate reuse never chooses a location: page hints, repeated quotes and
    numeric omissions retain the same complete candidate lists. Both entry and
    candidate/word-reference limits bound the cache; oversized lists are computed normally.
    A new verification creates a new index, so documents and later edits cannot
    inherit an earlier document's source positions or grounding decisions.
    """

    MAX_QUOTES = 256
    MAX_REFERENCES = 8192

    def __init__(self, document: Document) -> None:
        self._pages = [_PageIndex(page) for page in document.pages]
        self._cache: OrderedDict[tuple[str, int | None], tuple[GroundingMatch, ...]] = OrderedDict()
        self._references = 0

    def candidates(self, quote: str, *, hint_page: int | None = None) -> list[GroundingMatch]:
        key = (quote, hint_page)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return list(cached)
        pages = sorted(self._pages, key=lambda index: index.page.number != hint_page)
        matches = _candidates_in_pages(quote, pages)
        references = len(matches) + sum(len(match.words) for match in matches)
        if references <= self.MAX_REFERENCES:
            while self._cache and (
                len(self._cache) >= self.MAX_QUOTES
                or self._references + references > self.MAX_REFERENCES
            ):
                _, removed = self._cache.popitem(last=False)
                self._references -= len(removed) + sum(len(match.words) for match in removed)
            self._cache[key] = tuple(matches)
            self._references += references
        return matches


def _candidates_in_pages(quote: str, pages: list[_PageIndex]) -> list[GroundingMatch]:

    exact: list[GroundingMatch] = []
    for page in pages:
        exact.extend(_word_aligned_occurrences(quote, page))
    if exact:
        return exact

    folded: list[GroundingMatch] = []
    for page in pages:
        folded.extend(_word_aligned_occurrences(quote, page, fold_case=True))
    if folded:
        return folded

    by_value: list[GroundingMatch] = []
    for page in pages:
        by_value.extend(_value_occurrences(quote, page))
    if by_value:
        return by_value

    best_fuzzy: GroundingMatch | None = None
    for page in pages:
        match = _fuzzy_match(quote, page)
        if match is not None and (best_fuzzy is None or match.score > best_fuzzy.score):
            best_fuzzy = match
    return [best_fuzzy] if best_fuzzy is not None else []


def nearest_candidate(candidates: list[GroundingMatch], hint: GroundingMatch) -> GroundingMatch:
    """Pick whichever of several ambiguous `candidates` is closest to
    `hint` - same page first, then smallest vertical distance between
    their word tops. This ranking helper always chooses, even across pages or
    on a tie. Verification uses `unique_row_candidate` instead: proximity
    alone cannot establish a quote's location."""

    def distance(candidate: GroundingMatch) -> tuple[int, float]:
        same_page = 0 if candidate.page_number == hint.page_number else 1
        return (same_page, abs(candidate.top - hint.top))

    return min(candidates, key=distance)


def unique_row_candidate(
    candidates: list[GroundingMatch], hint: GroundingMatch
) -> GroundingMatch | None:
    """Resolve only one occurrence sharing the hint's actual visual line.

    Every word in both matches must share a vertical band at least half the
    shortest word's height, on the same page. This tolerates modest OCR skew
    without treating the nearest *different* row as evidence. A multiline
    quote cannot use its average height to invent an anchor between lines.
    Two matching columns remain ambiguous, even if one is slightly closer.

    This locates words, not table cells or semantic field roles. The caller
    must supply a strong hint whose value is independently supported.
    """
    local = []
    for candidate in candidates:
        if candidate.page_number != hint.page_number or not hint.words or not candidate.words:
            continue
        boxes = [word.bbox for word in (*hint.words, *candidate.words)]
        if any(
            not all(isfinite(v) for v in (box.x0, box.x1, box.top, box.bottom))
            or box.height <= 0
            or box.width <= 0
            for box in boxes
        ):
            continue
        overlap = min(box.bottom for box in boxes) - max(box.top for box in boxes)
        if overlap > 0 and overlap >= min(box.height for box in boxes) / 2:
            local.append(candidate)
    return local[0] if len(local) == 1 else None


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
