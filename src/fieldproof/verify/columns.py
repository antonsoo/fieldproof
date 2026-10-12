"""Conservative column observations from complete, explicitly named header rows.

No inferred column boundaries or unlabeled tables: a value must horizontally
intersect exactly one header. Missing/ambiguous evidence never upgrades a field.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING, Any, Literal

from fieldproof.document.model import BBox, Document, Word
from fieldproof.ground.align import GroundingMatch
from fieldproof.ground.values import NumberStyle, number_tokens
from fieldproof.verify.rows import RowEvidenceCheck, RowEvidenceRule
from fieldproof.verify.value_checks import check_number

if TYPE_CHECKING:
    from fieldproof.verify.engine import FieldVerification


@dataclass(frozen=True)
class ColumnEvidenceCheck:
    field: str
    status: Literal["aligned", "contradictory", "unavailable"]
    reason: str
    observed_column: str | None = None
    headers: dict[str, dict[str, Any]] | None = None
    value_locations: list[dict[str, Any]] = dataclass_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _box(words: tuple[Word, ...]) -> BBox:
    box = words[0].bbox
    for word in words[1:]:
        box = box.union(word.bbox)
    return box


def _location(page: int, words: tuple[Word, ...]) -> dict[str, Any]:
    return {
        "page": page,
        "text": " ".join(word.text for word in words),
        "start": min(word.start for word in words),
        "end": max(word.end for word in words),
        "rects": [_box(words).to_dict()],
    }


def _lines(words: list[Word]) -> list[tuple[Word, ...]]:
    # A malformed box makes this page's layout unavailable, rather than silently
    # removing words that could have disambiguated a header or interrupted a table.
    if any(
        not all(math.isfinite(v) for v in (w.bbox.x0, w.bbox.x1, w.bbox.top, w.bbox.bottom))
        or w.bbox.width <= 0
        or w.bbox.height <= 0
        for w in words
    ):
        return []
    lines: list[tuple[Word, ...]] = []
    current: list[Word] = []
    bottom = height = 0.0
    for word in sorted(words, key=lambda w: (w.bbox.top, w.bbox.x0, w.start)):
        if (
            current
            and min(bottom, word.bbox.bottom) - word.bbox.top < min(height, word.bbox.height) / 2
        ):
            lines.append(tuple(sorted(current, key=lambda w: (w.bbox.x0, w.start))))
            current = []
        bottom = min(bottom, word.bbox.bottom) if current else word.bbox.bottom
        height = min(height, word.bbox.height) if current else word.bbox.height
        current.append(word)
    if current:
        lines.append(tuple(sorted(current, key=lambda w: (w.bbox.x0, w.start))))
    return lines


def _header(line: tuple[Word, ...], rule: RowEvidenceRule) -> dict[str, tuple[Word, ...]] | None:
    assert rule.column_headers is not None
    spellings = [
        (name, tuple(label.casefold().split()))
        for name, labels in rule.column_headers.items()
        for label in labels
    ]
    text = tuple(word.text.casefold() for word in line)
    matches = []

    def visit(start: int, found: dict[str, tuple[Word, ...]]) -> None:
        if start == len(line):
            if set(found) == set(rule.column_headers or {}):
                matches.append(found)
            return
        for name, spelling in spellings:
            end = start + len(spelling)
            words = line[start:end]
            if name in found or text[start:end] != spelling:
                continue
            # "Unit" and "price" at opposite sides of a page are not one label.
            if any(
                b.bbox.x0 - a.bbox.x1 > 2 * min(a.bbox.height, b.bbox.height)
                for a, b in zip(words, words[1:], strict=False)
            ):
                continue
            visit(end, {**found, name: words})

    visit(0, {})
    if len(matches) != 1:
        return None
    found = matches[0]
    boxes = sorted((_box(words) for words in found.values()), key=lambda box: box.x0)
    if any(a.x1 >= b.x0 for a, b in zip(boxes, boxes[1:], strict=False)):
        return None
    return found


def _column(box: BBox, headers: dict[str, tuple[Word, ...]]) -> str | None:
    aligned = []
    for name, words in headers.items():
        header = _box(words)
        overlap = min(box.x1, header.x1) - max(box.x0, header.x0)
        if overlap > 0 and overlap >= min(box.width, header.width) / 2:
            aligned.append(name)
    return aligned[0] if len(aligned) == 1 else None


def _table_line(line: tuple[Word, ...], headers: dict[str, tuple[Word, ...]], anchor: str) -> bool:
    # Refuse to carry an old header across prose, totals, or an incomplete row.
    # This deliberately leaves wrapped/sparse tables unresolved.
    observed = {
        _column(word.bbox, headers)
        for word in line
        if any(token.readings() for token in number_tokens(word.text))
    }
    return set(headers) - {anchor} <= observed and any(
        any(c.isalpha() for c in word.text) and _column(word.bbox, headers) == anchor
        for word in line
    )


class ColumnEvidenceIndex:
    """Per-verification layout cache; never reused across document edits."""

    def __init__(self, document: Document) -> None:
        self.document = document
        self.lines: dict[int, list[tuple[Word, ...]]] = {}
        self.word_lines: dict[int, dict[tuple[int, int], int]] = {}
        self.headers: dict[
            tuple[int, tuple[tuple[str, tuple[str, ...]], ...]],
            list[tuple[int, dict[str, tuple[Word, ...]]]],
        ] = {}
        self.table_ends: dict[
            tuple[tuple[int, tuple[tuple[str, tuple[str, ...]], ...]], int, str], int
        ] = {}

    def check(
        self,
        row: RowEvidenceCheck,
        rule: RowEvidenceRule,
        result: FieldVerification | None,
        match: GroundingMatch | None,
        anchor: GroundingMatch | None,
        style: NumberStyle | None,
    ) -> ColumnEvidenceCheck:
        def unavailable(reason: str) -> ColumnEvidenceCheck:
            return ColumnEvidenceCheck(row.field, "unavailable", reason)

        if row.status != "same_line" or result is None or match is None or anchor is None:
            return unavailable(
                "column evidence requires strongly supported quotes on one item line"
            )
        if isinstance(result.value, bool) or not isinstance(result.value, int | float):
            return unavailable("column evidence currently checks numeric row fields only")
        assert rule.column_headers is not None
        page = match.page_number
        if page not in self.lines:
            self.lines[page] = _lines(self.document.page(page).words)
            self.word_lines[page] = {
                (word.start, word.end): i
                for i, line in enumerate(self.lines[page])
                for word in line
            }
        lines = self.lines[page]
        key = (page, tuple(sorted(rule.column_headers.items())))
        if key not in self.headers:
            self.headers[key] = [
                (i, header)
                for i, line in enumerate(lines)
                if (header := _header(line, rule)) is not None
            ]
        anchor_words = tuple(anchor.words)
        if not anchor_words:
            return unavailable("the item anchor has no word geometry")
        anchor_box = _box(anchor_words)
        candidates = [
            (i, header)
            for i, header in self.headers[key]
            if _box(lines[i]).bottom <= anchor_box.top
        ]
        if not candidates:
            return unavailable("no complete, unambiguous configured header row above this item")
        index, headers = candidates[-1]
        if _column(anchor_box, headers) != rule.anchor:
            return unavailable("the item description does not align with its configured header")
        end_key = (key, index, rule.anchor)
        if end_key not in self.table_ends:
            end = index
            for i in range(index + 1, len(lines)):
                if not _table_line(lines[i], headers, rule.anchor):
                    break
                end = i
            self.table_ends[end_key] = end
        anchor_lines = {self.word_lines[page].get((w.start, w.end), -1) for w in anchor_words}
        if (
            len(anchor_lines) != 1
            or not index < next(iter(anchor_lines)) <= self.table_ends[end_key]
        ):
            return unavailable(
                "the header and item are not connected by complete aligned table rows"
            )
        values = []
        columns = set()
        for token in number_tokens(match.matched_text):
            spelling = match.matched_text[token.start : token.end]
            if not check_number(result.value, spelling, number_style=style).supported:
                continue
            words = tuple(
                word
                for word in match.words
                if word.end > match.start + token.start and word.start < match.start + token.end
            )
            if not words:
                return unavailable("a supporting numeric token has no word geometry")
            values.append(_location(page, words))
            columns.add(_column(_box(words), headers))
        locations = {name: _location(page, words) for name, words in headers.items()}
        if not values or None in columns or len(columns) != 1:
            return ColumnEvidenceCheck(
                row.field,
                "unavailable",
                "supporting numeric tokens do not align with exactly one configured column",
                headers=locations,
                value_locations=values,
            )
        observed = columns.pop()
        expected = row.field.rsplit(".", 1)[1]
        assert observed is not None
        status: Literal["aligned", "contradictory"] = (
            "aligned" if observed == expected else "contradictory"
        )
        reason = (
            f"the supported number aligns with header {locations[observed]['text']!r} "
            f"({observed}), not {locations[expected]['text']!r} ({expected}), on page {page}"
            if status == "contradictory"
            else f"the supported number aligns with header {locations[expected]['text']!r} "
            f"on page {page}; alignment alone does not establish semantic correctness"
        )
        return ColumnEvidenceCheck(row.field, status, reason, observed, locations, values)
