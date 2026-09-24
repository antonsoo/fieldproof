"""Value-vs-evidence consistency: does the extracted value actually say what
the cited quote says?

Grounding only proves a quote exists on the page - it says nothing about
whether the *value* the model attached to it is correct. A model can (and
occasionally does) quote a real sentence and then attach the wrong number to
it. This module re-derives a value from the matched evidence text
independently - parsing a number, a date, or fuzzy-comparing a string - and
flags a mismatch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from rapidfuzz import fuzz

from fieldproof.ground.normalize import normalize

#: Absolute tolerance (in the field's own units, e.g. dollars) for numeric
#: value-vs-evidence comparisons - covers rounding in how the model or the
#: document itself formats cents.
NUMBER_TOLERANCE = 0.01

#: Below this rapidfuzz ratio (0-100), a string value is not considered
#: supported by its evidence text.
STRING_MATCH_THRESHOLD = 82.0

_MONEY_STRIP = re.compile(r"[^0-9.\-]")

#: A currency/plain-number token, optionally wrapped in parens (accounting
#: negative) or followed by "%" (so a rate like "8.5%" can be told apart
#: from the dollar amount next to it, e.g. "Tax (8.5%) $208.93").
_NUMBER_TOKEN = re.compile(r"\(?-?\$?\d[\d,]*(?:\.\d+)?\)?%?")

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d/%m/%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
    "%Y/%m/%d",
)

#: Date-shaped substrings to search for inside free text (e.g. "Issue Date:
#: January 1, 2026") - evidence is a verbatim quote, so it often carries a
#: label or surrounding words the schema's ISO-8601 value never does; a full
#: strptime match would reject that and never find the date at all.
_DATE_SEARCH_PATTERNS = (
    re.compile(r"\d{4}-\d{2}-\d{2}"),
    re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}"),
    re.compile(r"[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}"),
    re.compile(r"\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4}"),
)


@dataclass(frozen=True, slots=True)
class ValueCheckResult:
    supported: bool
    reason: str = ""


def parse_number(text: str) -> float | None:
    """Best-effort extraction of a number from free text: strips currency
    symbols and thousands separators, treats parenthesized amounts (an
    accounting convention) as negative, and - since evidence is a verbatim
    quote that often carries a label or an unrelated rate next to the real
    amount, e.g. "Tax (8.5%) $208.93" - prefers the last non-percentage
    number token over the first."""
    text = text.strip()
    if not text:
        return None

    if text.startswith("(") and text.endswith(")"):
        inner = _MONEY_STRIP.sub("", text[1:-1].replace(",", ""))
        if inner and inner not in {"-", "."}:
            try:
                return -abs(float(inner))
            except ValueError:
                pass

    matches = list(_NUMBER_TOKEN.finditer(text))
    non_percent = [m for m in matches if not m.group(0).endswith("%")]
    candidates = non_percent or matches
    if not candidates:
        return None

    token = candidates[-1].group(0)
    negative = token.startswith("(") or token.endswith(")")
    cleaned = _MONEY_STRIP.sub("", token.replace(",", ""))
    if not cleaned or cleaned in {"-", "."}:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return -abs(value) if negative else value


def parse_date(text: str) -> date | None:
    """Parse a date from either ISO-8601 (what the schema asks the model
    for) or a handful of common document formats (what evidence text, taken
    verbatim from the page, is more likely to contain). Tries a full-string
    match first; if that fails, searches for a date-shaped substring within
    surrounding text like "Issue Date: January 1, 2026"."""
    stripped = text.strip()
    candidate = _try_formats(stripped)
    if candidate is not None:
        return candidate

    for pattern in _DATE_SEARCH_PATTERNS:
        match = pattern.search(stripped)
        if match is None:
            continue
        candidate = _try_formats(match.group(0))
        if candidate is not None:
            return candidate
    return None


def _try_formats(text: str) -> date | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def check_number(value: float, evidence_text: str) -> ValueCheckResult:
    found = parse_number(evidence_text)
    if found is None:
        return ValueCheckResult(False, f"could not parse a number from evidence {evidence_text!r}")
    if abs(found - value) <= NUMBER_TOLERANCE:
        return ValueCheckResult(True)
    return ValueCheckResult(
        False, f"value {value:g} does not match {found:g} parsed from the evidence"
    )


def check_date(value: str, evidence_text: str) -> ValueCheckResult:
    claimed = parse_date(value)
    if claimed is None:
        return ValueCheckResult(False, f"value {value!r} is not a parseable ISO-8601 date")
    found = parse_date(evidence_text)
    if found is None:
        return ValueCheckResult(False, f"could not parse a date from evidence {evidence_text!r}")
    if claimed == found:
        return ValueCheckResult(True)
    return ValueCheckResult(
        False,
        f"value {claimed.isoformat()} does not match {found.isoformat()} parsed from the evidence",
    )


def check_string(
    value: str, evidence_text: str, *, threshold: float = STRING_MATCH_THRESHOLD
) -> ValueCheckResult:
    """Is `value` actually present in `evidence_text`? Evidence is a
    verbatim quote and is often longer than the value it supports (e.g. the
    quote "Invoice Number: INV-1001" for the value "INV-1001"), so this uses
    partial-ratio (best-matching substring) rather than whole-string
    similarity - a short value inside a longer quote should still verify."""
    normalized_value, normalized_evidence = normalize(value), normalize(evidence_text)
    score = fuzz.partial_ratio(normalized_value, normalized_evidence)
    if score >= threshold:
        return ValueCheckResult(True)
    return ValueCheckResult(
        False, f"value {value!r} is only {score:.0f}% similar to evidence {evidence_text!r}"
    )


def check_bool(value: bool, evidence_text: str) -> ValueCheckResult:
    text = normalize(evidence_text).lower()
    positive = any(w in text for w in ("yes", "true", "confirmed", "agreed", "approved"))
    negative = any(w in text for w in ("no", "false", "denied", "declined", "not "))
    if value and positive and not negative:
        return ValueCheckResult(True)
    if not value and negative:
        return ValueCheckResult(True)
    return ValueCheckResult(
        False, f"boolean value {value} is not clearly supported by evidence {evidence_text!r}"
    )
