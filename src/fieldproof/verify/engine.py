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

import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from fieldproof.document.model import Document
from fieldproof.ground.align import (
    GroundingMatch,
    find_candidates_in_document,
    letter_distance,
    nearest_candidate,
    rects_for_match,
)
from fieldproof.ground.values import NumberStyle, number_style
from fieldproof.schemas.base import iter_evidenced_fields
from fieldproof.verify.cross_field import CrossFieldIssue, check_cross_field
from fieldproof.verify.value_checks import (
    TOLERANT_MIN_LETTERS,
    DateOrder,
    ValueCheckResult,
    check_bool,
    check_date,
    check_number,
    check_string,
    numeric_date_order,
)

#: Matches the "row" a list-item field belongs to, e.g. "line_items[1]" out
#: of "line_items[1].quantity" - used to group sibling fields of the same
#: object so one can act as a locality hint for disambiguating another
#: (see `verify`).
_ROW_PREFIX_RE = re.compile(r"^(.*\[\d+\])\.")


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
        }


@dataclass
class VerificationReport:
    fields: list[FieldVerification]
    cross_field_issues: list[CrossFieldIssue]

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
        }


def _row_prefix(path: str) -> str | None:
    match = _ROW_PREFIX_RE.match(path)
    return match.group(1) if match else None


def verify(
    data: BaseModel,
    document: Document,
    *,
    text_edit_tolerance: int = 0,
    default_number_style: NumberStyle | None = None,
    default_date_order: DateOrder | None = None,
) -> VerificationReport:
    """Verify every `Evidenced` field under `data` against `document`.

    A number written "60.000" is sixty or sixty thousand, and a date written
    "03/04/2026" is 4 March or 3 April. Each is read the way the document's own
    numbers and dates settle it; where they settle nothing, neither reading is
    verified and the field is `needs_review`. `default_number_style` ("decimal":
    `.` is the decimal point, "thousands": it separates thousands) and
    `default_date_order` ("dmy" or "mdy") say how to read them in that case, for a
    caller who knows where the documents come from. A document that settles the
    question itself is read its own way whatever these say.

    By default a text value or quote that differs from the page in a letter or digit is
    `needs_review`, whatever the cause (a model's typo, or a model repairing an OCR error).
    `text_edit_tolerance=n` lets a text field of at least `TOLERANT_MIN_LETTERS` letters
    differ from the page by up to `n` letters in the quote and again in the value and stay
    `verified`, with what differed recorded in the field's `notes`. Numbers, dates and
    booleans are never given this tolerance.

    Fields are walked in schema-declaration order (`iter_evidenced_fields`),
    which for a list item means its fields come in the order they're
    declared on the model - e.g. `LineItem.description` before
    `LineItem.quantity`. The first field of each "row" (an indexed list
    item, e.g. `line_items[1]`) that grounds successfully becomes that
    row's locality anchor, used to disambiguate a later sibling field whose
    quote turns out to occur more than once on the page (see
    `_verify_field`'s `hint_match` and `fieldproof.ground.nearest_candidate`).
    """
    results: list[FieldVerification] = []
    row_anchors: dict[str, GroundingMatch] = {}
    # Whether this document writes numeric dates month or day first, if any of
    # its dates settles it; see `check_date`.
    if default_number_style not in (None, "decimal", "thousands"):
        raise ValueError(
            f'default_number_style must be "decimal" or "thousands", not {default_number_style!r}'
        )
    if default_date_order not in (None, "dmy", "mdy"):
        raise ValueError(f'default_date_order must be "dmy" or "mdy", not {default_date_order!r}')
    date_order = numeric_date_order(document.full_text()) or default_date_order
    # Likewise whether it writes "60.000" as sixty or sixty thousand; see `check_number`.
    style = number_style(document.full_text()) or default_number_style

    for path, evidenced in iter_evidenced_fields(data):
        prefix = _row_prefix(path)
        hint = row_anchors.get(prefix) if prefix else None

        result, match = _verify_field(
            path,
            evidenced,
            document,
            hint_match=hint,
            date_order=date_order,
            style=style,
            text_edit_tolerance=text_edit_tolerance,
        )
        results.append(result)

        if prefix is not None and prefix not in row_anchors and match is not None:
            row_anchors[prefix] = match

    cross_field_issues = check_cross_field(data)
    _apply_cross_field_issues(results, cross_field_issues)

    return VerificationReport(fields=results, cross_field_issues=cross_field_issues)


def _verify_field(
    path: str,
    evidenced: Any,
    document: Document,
    *,
    hint_match: GroundingMatch | None,
    date_order: DateOrder | None = None,
    style: NumberStyle | None = None,
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
        candidates.extend(find_candidates_in_document(quote, document, hint_page=evidenced.page))

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
    best_match: GroundingMatch | None

    if len(candidates) == 1:
        best_match = candidates[0]
    elif hint_match is not None:
        # Multiple occurrences of the same quote - prefer whichever is
        # closest to another field from the same row that's already been
        # grounded (e.g. this line item's description).
        best_match = nearest_candidate(candidates, hint_match)
    else:
        # Ambiguous with nothing nearby to disambiguate it against - don't
        # silently guess; a wrong guess here is exactly the "verified but
        # actually wrong" failure mode this tool exists to catch.
        best_match = None
        reasons.append(
            f"evidence {candidates[0].quote!r} is ambiguous (appears {len(candidates)} times); "
            "quote more context"
        )

    if best_match is None:
        result = FieldVerification(
            path=path, value=value, status=FieldStatus.NEEDS_REVIEW, reasons=reasons
        )
        return result, None

    notes: list[str] = []
    tolerant = (
        text_edit_tolerance > 0
        and isinstance(value, str)
        and not isinstance(value, bool)
        and "date" not in path.lower()
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
                "on the page but differs from it in letters or digits"
            )
        else:
            reasons.append(
                f"evidence match quality is only {best_match.score:.0f}/100 - the quote is a "
                "loose paraphrase or contains OCR-like noise"
            )

    check = _check_value(
        path,
        value,
        best_match.matched_text,
        date_order,
        style,
        text_edit_tolerance if tolerant else 0,
    )
    if not check.supported:
        reasons.append(check.reason)
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
    path: str,
    value: str | float | bool,
    evidence_text: str,
    date_order: DateOrder | None = None,
    style: NumberStyle | None = None,
    max_edits: int = 0,
) -> ValueCheckResult:
    if isinstance(value, bool):
        return check_bool(value, evidence_text)
    if isinstance(value, int | float):
        return check_number(float(value), evidence_text, number_style=style)
    if isinstance(value, str):
        if "date" in path.lower():
            return check_date(value, evidence_text, date_order=date_order)
        return check_string(value, evidence_text, max_edits=max_edits)
    return ValueCheckResult(True)


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
