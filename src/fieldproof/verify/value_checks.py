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
from typing import Literal

from rapidfuzz import fuzz

from fieldproof.ground.normalize import normalize
from fieldproof.ground.values import (
    NUMERIC_DATE,
    NumberStyle,
    number_readings,
    numeric_date_readings,
)

#: Largest absolute difference (in the field's own units, e.g. dollars) a numeric value may
#: have from the number the evidence shows. A value agrees with a number written to `p`
#: decimal places if it rounds to it, that is, if it is within half a unit of the last
#: place written, but never by more than this: a page that says 9.00 does not support 9.01.
NUMBER_TOLERANCE = 0.005

#: Below this rapidfuzz ratio (0-100), a string value is not considered
#: supported by its evidence text.
STRING_MATCH_THRESHOLD = 82.0

#: A currency/plain-number token, optionally wrapped in parens (accounting
#: negative) or followed by "%" (so a rate like "8.5%" can be told apart
#: from the dollar amount next to it, e.g. "Tax (8.5%) $208.93").
_NUMBER_TOKEN = re.compile(
    r"\(?-?\$?\d[\d,]*(?:(?:\.\d{3})+,\d{1,2}|(?:\.\d{3}){2,}(?!\d)|\.\d+)?\)?%?"
)

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d/%m/%Y",
    "%d/%m/%y",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%m-%d-%y",
    "%d-%m-%y",
    "%m.%d.%Y",
    "%d.%m.%Y",
    "%m.%d.%y",
    "%d.%m.%y",
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
    re.compile(r"\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}"),
    re.compile(r"[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}"),
    re.compile(r"\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4}"),
)


@dataclass(frozen=True, slots=True)
class ValueCheckResult:
    supported: bool
    reason: str = ""


def parse_all_numbers(text: str) -> list[float]:
    """Every plain (non-percentage) number in `text`, in reading order -
    strips currency symbols and thousands separators, and excludes rate-like
    tokens such as the "8.5" in "Tax (8.5%) $208.93". Evidence for a
    row-level field is often the whole row (e.g. "Fuel surcharge 1 210.50
    210.50" for a quantity of 1), so a value check needs to ask "does this
    number appear anywhere in the evidence", not just "is it the last
    number" - see `check_number`."""
    return [readings[0][0] for readings in _evidence_readings(text, None)]


def parse_number(text: str) -> float | None:
    """Best-effort extraction of a single number from free text - the last
    non-percentage number token, e.g. "208.93" from "Tax (8.5%) $208.93".
    For evidence that may contain several numbers where any one of them
    could be the value being checked (a whole line-item row, say), use
    `parse_all_numbers` / `check_number` instead."""
    values = parse_all_numbers(text)
    return values[-1] if values else None


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


def _evidence_readings(
    evidence_text: str, number_style: NumberStyle | None
) -> list[list[tuple[float, int]]]:
    """Per plain (non-percentage) number token in the evidence, every reading of it as
    (value, decimal places written)."""
    text = evidence_text.strip()
    if not text:
        return []
    matches = list(_NUMBER_TOKEN.finditer(text))
    non_percent = [m for m in matches if not m.group(0).endswith("%")]
    tokens: list[list[tuple[float, int]]] = []
    for m in non_percent or matches:
        raw = m.group(0)
        negative = raw.startswith("(") or raw.endswith(")") or raw.startswith("-")
        digits = raw.strip("()%-$")
        readings = [
            (-abs(float(r.value)) if negative else float(r.value), r.places)
            for r in number_readings(digits, number_style)
        ]
        if readings:
            tokens.append(readings)
    return tokens


def check_number(
    value: float, evidence_text: str, *, number_style: NumberStyle | None = None
) -> ValueCheckResult:
    """Does `value` appear anywhere among the numbers in `evidence_text`?
    Evidence for a row-level field can be the whole row (several numbers,
    one of which is the value), not just the value on its own - so this
    checks membership, not just "is it the last number parsed".

    A number is compared as a value, to the precision the page wrote it: 9.00
    supports 9 and 9.001, not 9.01. A token like "60.000" has two readings (sixty,
    sixty thousand) unless `number_style` says which way the document writes `.`
    (see `fieldproof.ground.values.number_style`); the value may match either."""
    tokens = _evidence_readings(evidence_text, number_style)
    if not tokens:
        return ValueCheckResult(False, f"could not parse a number from evidence {evidence_text!r}")
    readings = [r for token in tokens for r in token]
    for number, places in readings:
        if abs(number - value) <= min(0.5 * 10**-places, NUMBER_TOLERANCE) + 1e-9:
            return ValueCheckResult(True)
    closest = min((r[0] for r in readings), key=lambda c: abs(c - value))
    return ValueCheckResult(
        False, f"value {value:g} does not match {closest:g} parsed from the evidence"
    )


DateOrder = Literal["mdy", "dmy"]


def numeric_date_order(text: str) -> DateOrder | None:
    """The day/month order a document's numeric dates settle between them:
    "mdy" if some date's second part is over 12 (03/14/2026), "dmy" if some
    date's first part is (14/03/2026), None if no date settles it or the
    document mixes both."""
    month_first = day_first = False
    for m in NUMERIC_DATE.finditer(text):
        first, second = int(m.group(1)), int(m.group(3))
        if second > 12 >= first:
            month_first = True
        elif first > 12 >= second:
            day_first = True
    if month_first == day_first:
        return None
    return "mdy" if month_first else "dmy"


def check_date(
    value: str, evidence_text: str, *, date_order: DateOrder | None = None
) -> ValueCheckResult:
    """Does the evidence show the claimed date? A numeric date whose first two
    parts are both 12 or under (03/04/2026) reads as 4 March or 3 April; it is
    read in `date_order` (see `numeric_date_order`) when the document settles
    that, and otherwise can't verify a value on its own."""
    claimed = parse_date(value)
    if claimed is None:
        return ValueCheckResult(False, f"value {value!r} is not a parseable ISO-8601 date")

    numeric = _numeric_date_in(evidence_text.strip())
    if numeric is not None:
        readings = numeric_date_readings(numeric)
        if len(set(readings.values())) == 2:
            if date_order is not None:
                found = readings[date_order]
            elif claimed in readings.values():
                return ValueCheckResult(
                    False,
                    f"the evidence date {numeric.group(0)!r} reads as "
                    f"{readings['mdy'].isoformat()} (month first) or "
                    f"{readings['dmy'].isoformat()} (day first), and no other date on the "
                    "document settles which",
                )
            else:
                return ValueCheckResult(
                    False,
                    f"value {claimed.isoformat()} matches neither reading of "
                    f"{numeric.group(0)!r} ({readings['mdy'].isoformat()} or "
                    f"{readings['dmy'].isoformat()})",
                )
            if claimed == found:
                return ValueCheckResult(True)
            return ValueCheckResult(
                False,
                f"value {claimed.isoformat()} does not match {found.isoformat()} parsed from "
                f"the evidence (this document writes dates "
                f"{'month' if date_order == 'mdy' else 'day'} first)",
            )

    parsed = parse_date(evidence_text)
    if parsed is None:
        return ValueCheckResult(False, f"could not parse a date from evidence {evidence_text!r}")
    if claimed == parsed:
        return ValueCheckResult(True)
    return ValueCheckResult(
        False,
        f"value {claimed.isoformat()} does not match {parsed.isoformat()} parsed from the evidence",
    )


#: Formats in `_DATE_FORMATS` where day and month can't be confused.
_UNAMBIGUOUS_FORMATS = tuple(
    f for f in _DATE_FORMATS if not f.startswith(("%m/", "%d/", "%m-", "%d-", "%m.", "%d."))
)


def _numeric_date_in(text: str) -> re.Match[str] | None:
    """The day/month/year date `parse_date` would read from `text`, when that is
    a numeric one (it prefers a whole-string ISO or written-month date, then an
    ISO date inside the text, before a numeric one)."""
    for fmt in _UNAMBIGUOUS_FORMATS:
        try:
            datetime.strptime(text, fmt)
            return None
        except ValueError:
            continue
    if _DATE_SEARCH_PATTERNS[0].search(text):
        return None
    return NUMERIC_DATE.search(text)


_DIGIT_RUN = re.compile(r"\d+")


_WORD_RUN = re.compile(r"[^\W_]+")


def _alnum_words(text: str) -> list[str]:
    return _WORD_RUN.findall(normalize(text).casefold())


def _said_in(value_words: list[str], evidence_words: list[str]) -> bool:
    """Do the letters and digits of `value_words` read, in order and without any other, as
    a run of whole words of the evidence? Case, spacing and punctuation do not count:
    "D.I.Y." says "DIY", "Sdn. Bhd." says "SDN BHD". A letter that differs does."""
    target = "".join(value_words)
    if not target:
        return False
    for i in range(len(evidence_words)):
        built = ""
        for word in evidence_words[i:]:
            built += word
            if built == target:
                return True
            if not target.startswith(built):
                break
    return False


def check_string(
    value: str, evidence_text: str, *, threshold: float = STRING_MATCH_THRESHOLD
) -> ValueCheckResult:
    """Is `value` actually present in `evidence_text`? Evidence is a
    verbatim quote and is often longer than the value it supports (e.g. the
    quote "Invoice Number: INV-1001" for the value "INV-1001"), so the value
    only has to be a run of the evidence's words.

    The value is the model's rendering of what the evidence says, so it may differ
    in case, spacing and punctuation, and leave words out at either end. It may not
    differ in a letter or digit: "Northwind Traders" against evidence that reads
    "Northwlnd Traders" is 94% similar and is not what the page says. A value that is only
    similar to the evidence is reported as such and sent to review."""
    normalized_value, normalized_evidence = normalize(value), normalize(evidence_text)
    # Wording can differ a little and still be the same name. A number can't:
    # "NW-20260215" against a page that reads "NW-20260214" is 96% similar and
    # a different invoice. Every run of digits in the value has to be in the
    # evidence as written.
    evidence_numbers = set(_DIGIT_RUN.findall(normalized_evidence))
    for number in _DIGIT_RUN.findall(normalized_value):
        if number not in evidence_numbers:
            return ValueCheckResult(
                False,
                f"value {value!r} contains {number!r}, "
                f"which the evidence {evidence_text!r} does not",
            )
    if _said_in(_alnum_words(value), _alnum_words(evidence_text)):
        return ValueCheckResult(True)
    if not _alnum_words(value) and normalized_value and normalized_value in normalized_evidence:
        return ValueCheckResult(True)  # a value of nothing but punctuation, such as "-"
    score = fuzz.partial_ratio(normalized_value, normalized_evidence)
    if score >= threshold:
        return ValueCheckResult(
            False,
            f"value {value!r} is {score:.0f}% similar to evidence {evidence_text!r} but "
            "differs from it in letters or digits",
        )
    return ValueCheckResult(
        False, f"value {value!r} is only {score:.0f}% similar to evidence {evidence_text!r}"
    )


_POSITIVE_WORDS = frozenset({"yes", "true", "confirmed", "agreed", "approved"})
_NEGATIVE_WORDS = frozenset({"no", "not", "false", "denied", "declined"})
_WORD = re.compile(r"[a-z]+")


def check_bool(value: bool, evidence_text: str) -> ValueCheckResult:
    # Whole words: "no" inside "notice" or "November" is not a negation.
    words = set(_WORD.findall(normalize(evidence_text).lower()))
    positive = bool(words & _POSITIVE_WORDS)
    negative = bool(words & _NEGATIVE_WORDS)
    if value and positive and not negative:
        return ValueCheckResult(True)
    if not value and negative:
        return ValueCheckResult(True)
    return ValueCheckResult(
        False, f"boolean value {value} is not clearly supported by evidence {evidence_text!r}"
    )
