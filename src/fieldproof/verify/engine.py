"""Orchestrates grounding + value checks + cross-field rules into a
per-field verdict.

Every extracted field ends up in exactly one of three states:

- `verified` - its evidence was found on the page with a strong match, and
  the value agrees with what the evidence actually says.
- `needs_review` - evidence was found but the match was weak, or the value
  disagrees with the evidence, or a cross-field rule it participates in
  failed. Worth a human's attention, not necessarily wrong.
- `unsupported` - no evidence quote was provided, or none of the quotes
  could be located anywhere in the document. This is the strongest signal
  of a hallucinated field.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from fieldproof.document.model import Document
from fieldproof.ground.align import GroundingMatch, ground_quote, rects_for_match
from fieldproof.schemas.base import iter_evidenced_fields
from fieldproof.verify.cross_field import CrossFieldIssue, check_cross_field
from fieldproof.verify.value_checks import (
    ValueCheckResult,
    check_bool,
    check_date,
    check_number,
    check_string,
)


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


def verify(data: BaseModel, document: Document) -> VerificationReport:
    """Verify every `Evidenced` field under `data` against `document`."""
    results: list[FieldVerification] = []

    for path, evidenced in iter_evidenced_fields(data):
        results.append(_verify_field(path, evidenced, document))

    cross_field_issues = check_cross_field(data)
    _apply_cross_field_issues(results, cross_field_issues)

    return VerificationReport(fields=results, cross_field_issues=cross_field_issues)


def _verify_field(path: str, evidenced: Any, document: Document) -> FieldVerification:
    value = evidenced.value

    if not evidenced.evidence:
        return FieldVerification(
            path=path,
            value=value,
            status=FieldStatus.UNSUPPORTED,
            reasons=["no evidence quote was provided for this value"],
        )

    best_match: GroundingMatch | None = None
    for quote in evidenced.evidence:
        match = ground_quote(quote, document, hint_page=evidenced.page)
        if match is not None and (best_match is None or match.score > best_match.score):
            best_match = match

    if best_match is None:
        quoted = ", ".join(repr(q) for q in evidenced.evidence)
        return FieldVerification(
            path=path,
            value=value,
            status=FieldStatus.UNSUPPORTED,
            reasons=[f"none of the evidence quotes ({quoted}) could be located in the document"],
        )

    reasons: list[str] = []
    if not best_match.is_strong:
        reasons.append(
            f"evidence match quality is only {best_match.score:.0f}/100 - the quote is a loose "
            "paraphrase or contains OCR-like noise"
        )

    check = _check_value(path, value, best_match.matched_text)
    if not check.supported:
        reasons.append(check.reason)

    status = FieldStatus.NEEDS_REVIEW if reasons else FieldStatus.VERIFIED

    rects = [r.to_dict() for r in rects_for_match(best_match)]

    return FieldVerification(
        path=path,
        value=value,
        status=status,
        reasons=reasons,
        match_score=best_match.score,
        matched_text=best_match.matched_text,
        page=best_match.page_number,
        rects=rects,
    )


def _check_value(path: str, value: str | float | bool, evidence_text: str) -> ValueCheckResult:
    if isinstance(value, bool):
        return check_bool(value, evidence_text)
    if isinstance(value, int | float):
        return check_number(float(value), evidence_text)
    if isinstance(value, str):
        if "date" in path.lower():
            return check_date(value, evidence_text)
        return check_string(value, evidence_text)
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
