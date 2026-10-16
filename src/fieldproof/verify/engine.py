"""Orchestrates grounding + value checks + cross-field rules into a
per-field verdict.

Every extracted field ends up in exactly one of three states:

- `verified` - its evidence was found on the page, unambiguously, with a
  strong match, and the value agrees with what the evidence actually says.
- `needs_review` - evidence was found but the match was weak, the value
  disagrees with the evidence, a cross-field rule it participates in
  failed, or the quote is genuinely ambiguous (it occurs more than once
  and nothing nearby disambiguates it). Worth a human's attention, not
  necessarily wrong.
- `unsupported` - no evidence quote was provided, or none of the quotes
  could be located anywhere in the document. This is the strongest signal
  of a hallucinated field.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel

from fieldproof.document.model import Document, OcrProvenance, Page
from fieldproof.ground.align import (
    GroundingIndex,
    GroundingMatch,
    letter_distance,
    rects_for_match,
    unique_row_candidate,
)
from fieldproof.ground.lines import separate_lines
from fieldproof.ground.values import NumberStyle, number_styles
from fieldproof.schemas.base import Evidenced, EvidencedDate, EvidencedText, iter_evidenced_fields
from fieldproof.verify.columns import ColumnEvidenceCheck, ColumnEvidenceIndex
from fieldproof.verify.cross_field import CrossFieldCheck, CrossFieldIssue, audit_cross_field
from fieldproof.verify.rows import (
    RowEvidenceCheck,
    RowEvidenceRule,
    check_row_field,
    configured_rows,
    default_row_rules,
)
from fieldproof.verify.value_checks import (
    TOLERANT_MIN_LETTERS,
    DateOrder,
    ValueCheckResult,
    check_bool,
    check_date,
    check_number,
    check_string,
    numeric_date_orders,
)

#: Matches the "row" a list-item field belongs to, e.g. "line_items[1]" out
#: of "line_items[1].quantity" - used to group sibling fields of the same
#: object so one can act as a locality hint for disambiguating another
#: (see `verify`).
_ROW_PREFIX_RE = re.compile(r"^(.*\[\d+\])\.")
_QUOTED_MEMBER_RE = re.compile(r'\["(?:[^"\\]|\\.)*"\]')
_PATH_MEMBER_RE = re.compile(
    r'\[(?P<key>"(?:[^"\\]|\\.)*")\]|\[\d+\]|(?P<name>[^.\[\]]+)'
)
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _date_name_hint(path: str) -> bool:
    # Paths are emitted by iter_evidenced_fields. Numeric indices keep their
    # collection's name; a new model member or quoted mapping key replaces it.
    # Decode quoted members so punctuation/escapes cannot change the naming rule.
    name = ""
    for member in _PATH_MEMBER_RE.finditer(path):
        if (key := member.group("key")) is not None:
            name = json.loads(key)
        elif (field_name := member.group("name")) is not None:
            name = field_name
    words = re.split(r"[\W_\d]+", _CAMEL_BOUNDARY_RE.sub("_", name).casefold())
    return bool({"date", "dates", "birthdate", "birthdates"}.intersection(words))


class FieldStatus(StrEnum):
    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"
    UNSUPPORTED = "unsupported"


@dataclass
class FieldVerification:
    path: str
    value: str | float | bool
    status: FieldStatus
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    match_score: float | None = None
    matched_text: str | None = None
    page: int | None = None
    rects: list[dict[str, float]] = field(default_factory=list)
    declared_kind: Literal["date", "text"] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "value": self.value,
            "status": self.status.value,
            "reasons": self.reasons,
            **({"notes": self.notes} if self.notes else {}),
            "match_score": self.match_score,
            "matched_text": self.matched_text,
            "page": self.page,
            "rects": self.rects,
            **({"declared_kind": self.declared_kind} if self.declared_kind is not None else {}),
        }


@dataclass
class VerificationReport:
    fields: list[FieldVerification]
    cross_field_issues: list[CrossFieldIssue]
    cross_field_checks: list[CrossFieldCheck] = field(default_factory=list)
    row_checks: list[RowEvidenceCheck] = field(default_factory=list)
    ocr: OcrProvenance | None = None
    column_checks: list[ColumnEvidenceCheck] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in FieldStatus}
        for f in self.fields:
            counts[f.status.value] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "fields": [f.to_dict() for f in self.fields],
            "cross_field_issues": [
                {"fields": list(i.fields), "message": i.message} for i in self.cross_field_issues
            ],
            "counts": self.counts,
            "cross_field_checks": [check.to_dict() for check in self.cross_field_checks],
            "row_checks": [check.to_dict() for check in self.row_checks],
            "column_checks": [check.to_dict() for check in self.column_checks],
            **({"ocr": self.ocr.to_dict()} if self.ocr is not None else {}),
        }


def _row_prefix(path: str) -> str | None:
    # A literal mapping key such as "items[0].amount" is not a row position.
    # Mask quoted members without changing offsets before finding a real index.
    masked = _QUOTED_MEMBER_RE.sub(lambda match: "x" * len(match.group()), path)
    match = _ROW_PREFIX_RE.match(masked)
    return path[:match.end(1)] if match else None


def _validate_claim_value(path: str, evidenced: Evidenced) -> None:
    # Pydantic permits generic arguments outside a TypeVar's constraints, and
    # callers can mutate models after validation. Inspect the actual value
    # before grounding: a real quote is not a verification rule for an object.
    value = evidenced.value
    if isinstance(evidenced, EvidencedDate | EvidencedText) and not isinstance(value, str):
        raise ValueError(
            f"claim at {path!r} declares a string kind but has value type "
            f"{type(value).__name__}; supply a string value"
        )
    if not isinstance(value, str | int | float | bool):
        raise ValueError(
            f"claim at {path!r} has unsupported value type {type(value).__name__}; "
            "Evidenced values must be strings, integers, floats or booleans. "
            "Put containers outside Evidenced and represent an absent claim with "
            "an optional wrapper, not a null value"
        )


def _convention_text(page: Page) -> str:
    # Preserve offsets and separators: removing hidden text could join fragments
    # into a new number/date. Unpainted text cannot settle another field's policy.
    text = list(page.text)
    for word in page.words:
        if word.paint_requires_review:
            text[word.start : word.end] = " " * (word.end - word.start)
    return "".join(text)


def verify(
    data: BaseModel,
    document: Document,
    *,
    text_edit_tolerance: int = 0,
    default_number_style: NumberStyle | None = None,
    default_date_order: DateOrder | None = None,
    row_rules: Sequence[RowEvidenceRule] | None = None,
) -> VerificationReport:
    """Verify every `Evidenced` field under `data` against `document`.

    A number written "60.000" is sixty or sixty thousand, and a date written
    "03/04/2026" is 4 March or 3 April. Each is read the way the document's own
    numbers and dates settle it; where they settle nothing, neither reading is
    verified and the field is `needs_review`. `default_number_style` ("decimal":
    `.` is the decimal point, "thousands": it separates thousands) and
    `default_date_order` ("dmy" or "mdy") say how to read them in that case, for a
    caller who knows where the documents come from. A document that settles the
    question itself is read its own way whatever these say. Conflicting observed
    conventions leave ambiguous values in review even when a default is supplied;
    defaults fill absent evidence, not contradictory evidence.

    By default a text value or quote that differs from the page in a letter or digit is
    `needs_review`, whatever the cause (a model's typo, or a model repairing an OCR error).
    `text_edit_tolerance=n` lets a text field of at least `TOLERANT_MIN_LETTERS` letters
    differ from the page by up to `n` letters in the quote and again in the value and stay
    `verified`, with what differed recorded in the field's `notes`. Numbers, dates and
    booleans are never given this tolerance.

    `EvidencedDate` and `EvidencedText` declare string policy independently of
    field names, and the report records `declared_kind`. For plain `Evidenced[str]`,
    only the final named member supplies a hint: complete date/dates/birthdate(s)
    words, including snake_case and camelCase forms. Ancestor names do not set
    the kind; numeric positions retain their collection's name. Use an explicit
    wrapper when the name does not express the intended kind.

    Each present wrapper must hold a string, integer, float or boolean;
    explicit string kinds must hold strings. Other values raise `ValueError`
    with their field path before any grounding or report generation. Put
    containers outside the wrapper (e.g. `dict[str, Evidenced[str]]`), and use
    `Evidenced[str] | None` for an absent optional claim. No values are coerced.

    Fields are walked in schema-declaration order (`iter_evidenced_fields`),
    which for a list item means its fields come in the order they're
    declared on the model - e.g. `LineItem.description` before
    `LineItem.quantity`. The first strongly grounded, value-supported field
    of each indexed list item becomes its locality anchor. A later sibling's
    repeated quote resolves only if exactly one occurrence shares that
    anchor's visual line on the same page. Weak matches, including accepted
    text edits, cannot establish anchors. Arithmetic checks run afterwards
    and do not establish or change a location.

    Invoice and receipt line-item numbers additionally require a source
    location sharing their description's visual line, even for unique quotes.
    `row_rules` declares equivalent relationships for custom schemas; an empty
    sequence disables these checks. The report records same-line, separate,
    and unavailable evidence, preserving source locations for review. This
    spatial check does not establish table columns or semantic field roles.

    Invoice defaults also observe explicit Description / Qty / Unit price /
    Amount headers (and the declared label alternatives). Row rules may supply
    `column_headers` for custom schemas. A supported numeric quote aligned with
    another configured column requires review. Missing or ambiguous layouts
    remain unavailable in `column_checks`, without changing field verdicts.
    """
    results: list[FieldVerification] = []
    row_anchors: dict[str, tuple[str, GroundingMatch]] = {}
    # Whether this document writes numeric dates month or day first, if any of
    # its dates settles it; see `check_date`.
    if default_number_style not in (None, "decimal", "thousands"):
        raise ValueError(
            f'default_number_style must be "decimal" or "thousands", not {default_number_style!r}'
        )
    if default_date_order not in (None, "dmy", "mdy"):
        raise ValueError(f'default_date_order must be "dmy" or "mdy", not {default_date_order!r}')
    fields = dict(iter_evidenced_fields(data))
    for path, evidenced in fields.items():
        _validate_claim_value(path, evidenced)
    grounding = GroundingIndex(document)
    convention_pages = [(page, _convention_text(page)) for page in document.pages]
    orders = numeric_date_orders("\n".join(text for _, text in convention_pages))
    date_order = (
        next(iter(orders)) if len(orders) == 1 else default_date_order if not orders else None
    )
    # Likewise whether it writes "60.000" as sixty or sixty thousand; see `check_number`.
    numeric_text = "\n".join(separate_lines(text, page.words) for page, text in convention_pages)
    styles = number_styles(numeric_text)
    style = next(iter(styles)) if len(styles) == 1 else default_number_style if not styles else None

    rows = configured_rows(data, default_row_rules(data) if row_rules is None else tuple(row_rules))
    anchor_results: dict[str, tuple[FieldVerification, GroundingMatch | None]] = {}
    for row_prefix, rule in rows.items():
        anchor_path = f"{row_prefix}.{rule.anchor}"
        if anchor_path not in fields:
            continue
        anchor_result, anchor_match = _verify_field(
            anchor_path,
            fields[anchor_path],
            grounding,
            hint_match=None,
            hint_path=None,
            date_order=date_order,
            style=style,
            conflicting_date_orders=len(orders) > 1,
            conflicting_number_styles=len(styles) > 1,
            text_edit_tolerance=text_edit_tolerance,
        )
        anchor_results[anchor_path] = (anchor_result, anchor_match)
        if _can_anchor(anchor_result, anchor_match):
            assert anchor_match is not None
            row_anchors[row_prefix] = (anchor_path, anchor_match)

    matches: dict[str, GroundingMatch | None] = {}

    for path, evidenced in fields.items():
        prefix = _row_prefix(path)
        hint = row_anchors.get(prefix) if prefix else None

        result, match = anchor_results.get(path) or _verify_field(
            path,
            evidenced,
            grounding,
            hint_match=hint[1] if hint else None,
            hint_path=hint[0] if hint else None,
            date_order=date_order,
            style=style,
            conflicting_date_orders=len(orders) > 1,
            conflicting_number_styles=len(styles) > 1,
            text_edit_tolerance=text_edit_tolerance,
        )
        if isinstance(evidenced, EvidencedDate):
            result.declared_kind = "date"
        elif isinstance(evidenced, EvidencedText):
            result.declared_kind = "text"
        results.append(result)
        matches[path] = match

        if (
            prefix is not None
            and prefix not in rows
            and prefix not in row_anchors
            and _can_anchor(result, match)
        ):
            # Accepted edits are explicitly noted by the value check too: a
            # corrected value must not silently lend authority to another field.
            assert match is not None
            row_anchors[prefix] = (path, match)

    by_path = {result.path: result for result in results}
    row_checks = [
        check_row_field(
            f"{prefix}.{name}",
            f"{prefix}.{rule.anchor}",
            by_path.get(f"{prefix}.{name}"),
            by_path.get(f"{prefix}.{rule.anchor}"),
            matches.get(f"{prefix}.{name}"),
            matches.get(f"{prefix}.{rule.anchor}"),
            anchor_trusted=prefix in row_anchors,
        )
        for prefix, rule in rows.items()
        for name in rule.fields
    ]
    # Capture every source verdict before changing any final field verdict.
    columns = ColumnEvidenceIndex(document)
    column_checks = [
        columns.check(
            check,
            rule,
            by_path.get(check.field),
            matches.get(check.field),
            matches.get(check.anchor),
            style,
        )
        for check in row_checks
        if (prefix := _row_prefix(check.field)) is not None
        and (rule := rows[prefix]).column_headers is not None
    ]
    for check in row_checks:
        checked_result = by_path.get(check.field)
        if (
            checked_result is not None
            and checked_result.status == FieldStatus.VERIFIED
            and check.status != "same_line"
        ):
            checked_result.status = FieldStatus.NEEDS_REVIEW
            checked_result.reasons.append(
                f"row association needs review: {check.reason}; check the item assignment "
                "or a wrapped table layout"
            )

    for column_check in column_checks:
        checked_result = by_path.get(column_check.field)
        if checked_result is not None and column_check.status == "contradictory":
            if checked_result.status == FieldStatus.VERIFIED:
                checked_result.status = FieldStatus.NEEDS_REVIEW
            checked_result.reasons.append(f"column association needs review: {column_check.reason}")

    cross_field_checks = audit_cross_field(data)
    cross_field_issues = [issue for check in cross_field_checks if (issue := check.issue())]
    _apply_cross_field_issues(results, cross_field_issues)

    return VerificationReport(
        fields=results,
        cross_field_issues=cross_field_issues,
        cross_field_checks=cross_field_checks,
        row_checks=row_checks,
        column_checks=column_checks,
        ocr=document.ocr,
    )


def _can_anchor(result: FieldVerification, match: GroundingMatch | None) -> bool:
    return (
        match is not None
        and match.is_strong
        and result.status == FieldStatus.VERIFIED
        and not result.notes
    )


def _verify_field(
    path: str,
    evidenced: Any,
    grounding: GroundingIndex,
    *,
    hint_match: GroundingMatch | None,
    hint_path: str | None,
    date_order: DateOrder | None = None,
    style: NumberStyle | None = None,
    conflicting_date_orders: bool = False,
    conflicting_number_styles: bool = False,
    text_edit_tolerance: int = 0,
) -> tuple[FieldVerification, GroundingMatch | None]:
    value = evidenced.value

    if not evidenced.evidence:
        result = FieldVerification(
            path=path,
            value=value,
            status=FieldStatus.UNSUPPORTED,
            reasons=["no evidence quote was provided for this value"],
        )
        return result, None

    candidates: list[GroundingMatch] = []
    for quote in evidenced.evidence:
        candidates.extend(grounding.candidates(quote, hint_page=evidenced.page))

    if not candidates:
        quoted = ", ".join(repr(q) for q in evidenced.evidence)
        result = FieldVerification(
            path=path,
            value=value,
            status=FieldStatus.UNSUPPORTED,
            reasons=[f"none of the evidence quotes ({quoted}) could be located in the document"],
        )
        return result, None

    reasons: list[str] = []
    notes: list[str] = []
    best_match: GroundingMatch | None

    if len(candidates) == 1:
        best_match = candidates[0]
    elif hint_match is not None:
        best_match = unique_row_candidate(candidates, hint_match)
        if best_match is not None:
            notes.append(
                f"located one of {len(candidates)} evidence occurrences on the same visual "
                f"line as {hint_path} (page {hint_match.page_number}); "
                "this does not establish the table column or field role"
            )
    else:
        # Ambiguous with nothing nearby to disambiguate it against - don't
        # silently guess; a wrong guess here is exactly the "verified but
        # actually wrong" failure mode this tool exists to catch.
        best_match = None

    if best_match is None:
        detail = (
            f"no unique occurrence shares the visual line of {hint_path} "
            f"on page {hint_match.page_number}"
            if hint_match is not None
            else "no strongly grounded, value-supported sibling establishes a row"
        )
        reasons.append(
            f"evidence {candidates[0].quote!r} is ambiguous (appears {len(candidates)} times); "
            f"{detail}; quote more context"
        )
        result = FieldVerification(
            path=path, value=value, status=FieldStatus.NEEDS_REVIEW, reasons=reasons
        )
        return result, None

    unpainted_modes = sorted({
        word.render_mode for word in best_match.words
        if word.render_mode in (3, 7)
    })
    if unpainted_modes:
        modes = ", ".join(str(mode) for mode in unpainted_modes)
        reasons.append(
            f"evidence includes unpainted PDF text (rendering mode {modes}: invisible or "
            "clipping only); matching this text layer does not establish what is visible "
            "on the page; review the rendered document"
        )
    if any(word.zero_opacity for word in best_match.words):
        reasons.append(
            "evidence includes PDF text with zero opacity; matching this transparent "
            "text layer does not establish what is visible on the page; review the "
            "rendered document"
        )
    if any(word.clip_risk for word in best_match.words):
        reasons.append(
            "evidence includes PDF text whose bounds cross a clipping boundary; "
            "the complete quote may not be visible on the page; review the rendered document"
        )
    if any(word.raster_state == "no_contribution" for word in best_match.words):
        reasons.append(
            "some quoted PDF characters have no observed native-text paint contribution "
            "inside their bounds; the text layer alone does not establish what is readable "
            "there; review the page"
        )
    if any(
        word.paint_requires_review
        and not (word.unpainted or word.clip_risk or word.raster_state == "no_contribution")
        for word in best_match.words
    ):
        reasons.append(
            "evidence includes native PDF text without a completed rendering contribution check; "
            "visibility is unverified; review the source or reload the PDF"
        )

    date_value = isinstance(value, str) and (
        isinstance(evidenced, EvidencedDate)
        or (not isinstance(evidenced, EvidencedText) and _date_name_hint(path))
    )
    tolerant = (
        text_edit_tolerance > 0
        and isinstance(value, str)
        and not isinstance(value, bool)
        and not date_value
    )
    if not best_match.is_strong:
        distance = letter_distance(best_match.quote, best_match.matched_text)
        if (
            tolerant
            and best_match.letters_agree is False
            and distance <= text_edit_tolerance
            and len(best_match.quote) >= TOLERANT_MIN_LETTERS
        ):
            notes.append(
                f"the quote differs from the page text {best_match.matched_text!r} by "
                f"{distance} letter{'s' if distance != 1 else ''} (accepted: "
                f"text_edit_tolerance={text_edit_tolerance})"
            )
        elif best_match.letters_agree is False:
            reasons.append(
                f"the quote is {best_match.score:.0f}/100 like {best_match.matched_text!r} "
                "on the page but differs from it in letters or digits, or numeric signs/units"
            )
        else:
            reasons.append(
                f"evidence match quality is only {best_match.score:.0f}/100 - the quote is a "
                "loose paraphrase or contains OCR-like noise"
            )

    value_text = best_match.matched_text
    if isinstance(value, int | float) and not isinstance(value, bool):
        value_text = separate_lines(value_text, best_match.words, start=best_match.start)
    check = _check_value(
        value,
        value_text,
        date_order,
        style,
        text_edit_tolerance if tolerant else 0,
        date_value=date_value,
    )
    if not check.supported:
        reasons.append(check.reason)
        if (
            conflicting_number_styles
            and isinstance(value, int | float)
            and not isinstance(value, bool)
        ):
            reasons.append(
                "the document contains both decimal-point and dot-thousands conventions; "
                "a document-wide number default cannot settle conflicting evidence"
            )
        elif conflicting_date_orders and date_value:
            reasons.append(
                "the document contains both month-first and day-first date conventions; "
                "a document-wide date default cannot settle conflicting evidence"
            )
    elif check.reason:
        notes.append(check.reason)

    status = FieldStatus.NEEDS_REVIEW if reasons else FieldStatus.VERIFIED

    rects = [r.to_dict() for r in rects_for_match(best_match)]

    result = FieldVerification(
        path=path,
        value=value,
        status=status,
        reasons=reasons,
        notes=notes,
        match_score=best_match.score,
        matched_text=best_match.matched_text,
        page=best_match.page_number,
        rects=rects,
    )
    return result, best_match


def _check_value(
    value: str | float | bool,
    evidence_text: str,
    date_order: DateOrder | None = None,
    style: NumberStyle | None = None,
    max_edits: int = 0,
    *,
    date_value: bool = False,
) -> ValueCheckResult:
    if isinstance(value, bool):
        return check_bool(value, evidence_text)
    if isinstance(value, int | float):
        return check_number(value, evidence_text, number_style=style)
    if isinstance(value, str):
        if date_value:
            return check_date(value, evidence_text, date_order=date_order)
        return check_string(value, evidence_text, max_edits=max_edits)
    raise TypeError(f"value type {type(value).__name__} has no verification rule")


def _apply_cross_field_issues(
    results: list[FieldVerification], issues: list[CrossFieldIssue]
) -> None:
    issue_reasons: dict[str, list[str]] = defaultdict(list)
    for issue in issues:
        for path in issue.fields:
            issue_reasons[path].append(issue.message)

    by_path = {r.path: r for r in results}
    for path, reasons in issue_reasons.items():
        result = by_path.get(path)
        if result is None:
            continue
        result.reasons.extend(reasons)
        if result.status == FieldStatus.VERIFIED:
            result.status = FieldStatus.NEEDS_REVIEW
