"""Read numbers and dates the way a page writes them, as values.

Grounding and verification both need to know that "60.000", "60,000" and "60000" can be
the same amount and that "25/12/2018", "25-12-18" and "2018-12-25" can be the same day.
Comparing such strings by edit distance is wrong in both directions (the strings that are
the same value look different; "19.80" and "18.90" look alike and are not), so this module
turns them into values and leaves the comparison to the caller.

Nothing here knows about a document: the choices a single token cannot settle (does "1.234"
mean one and a bit or one thousand two hundred and thirty-four, is "03/04/2026" March or
April) are returned as every reading the token has, and `number_style` and
`fieldproof.verify.numeric_date_order` say which of them the document settles.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fieldproof.ground.normalize import normalize_with_map

NumberStyle = Literal["decimal", "thousands"]

#: What a token of digits and separators looks like. Currency symbols, letters and a
#: percent sign are stripped by the caller; a token is only the number.
_COMMA_THOUSANDS = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
_DOT_THOUSANDS_MANY = re.compile(r"^\d{1,3}(?:\.\d{3}){2,}(?:,\d{1,2})?$")
_DOT_THOUSANDS_ONE = re.compile(r"^[1-9]\d{0,2}\.\d{3}$")
_DOT_THOUSANDS_COMMA_DECIMAL = re.compile(r"^\d{1,3}(?:\.\d{3})+,\d{1,2}$")
_COMMA_DECIMAL = re.compile(r"^\d*,\d{1,2}$")
_PLAIN = re.compile(r"^(?:\d+(?:\.\d+)?|\.\d+)$")
_INDIAN_THOUSANDS = re.compile(r"^\d{1,2}(?:,\d{2})+,\d{3}(?:\.\d+)?$")


@dataclass(frozen=True, slots=True)
class NumberReading:
    """One way to read a numeric token: its value and the decimal places it was written to."""

    value: Decimal
    places: int


def number_readings(token: str, style: NumberStyle | None = None) -> list[NumberReading]:
    """Every reading of `token` (digits with `.` and `,` separators, no sign, no symbols).

    "1,234.50" and "1.234,50" have one reading each. "60,000" is sixty thousand. "60.000"
    is sixty with three decimals or sixty thousand: both readings come back unless `style`
    (see `number_style`) says the document writes `.` as the decimal point ("decimal") or
    as the thousands separator ("thousands"). Returns [] for anything that is not a number.
    """
    if _COMMA_THOUSANDS.match(token):
        whole, _, frac = token.partition(".")
        return [
            NumberReading(Decimal(whole.replace(",", "") + ("." + frac if frac else "")), len(frac))
        ]
    if _DOT_THOUSANDS_COMMA_DECIMAL.match(token):
        whole, _, frac = token.partition(",")
        return [NumberReading(Decimal(whole.replace(".", "") + "." + frac), len(frac))]
    if _DOT_THOUSANDS_MANY.match(token):
        whole, _, frac = token.partition(",")
        return [
            NumberReading(Decimal(whole.replace(".", "") + ("." + frac if frac else "")), len(frac))
        ]
    if _COMMA_DECIMAL.match(token):
        whole, _, frac = token.partition(",")
        return [NumberReading(Decimal(whole + "." + frac), len(frac))]
    if _PLAIN.match(token):
        literal = NumberReading(Decimal(token), len(token.partition(".")[2]))
        if _DOT_THOUSANDS_ONE.match(token):
            thousands = NumberReading(Decimal(token.replace(".", "")), 0)
            if style == "decimal":
                return [literal]
            if style == "thousands":
                return [thousands]
            return [literal, thousands]
        return [literal]
    if _INDIAN_THOUSANDS.match(token):
        return [NumberReading(Decimal(token.replace(",", "")), len(token.partition(".")[2]))]
    return []


_COMMA_THOUSANDS_TOKEN = re.compile(r"(?<![\d.,])\d{1,3}(?:,\d{3})+\.\d{1,2}(?![\d.,])")
_DOT_THOUSANDS_TOKEN = re.compile(r"(?<![\d.,])\d{1,3}(?:\.\d{3}){2,}(?![\d.,])")
_DOT_THOUSANDS_DECIMAL_TOKEN = re.compile(r"(?<![\d.,])\d{1,3}(?:\.\d{3})+,\d{1,2}(?![\d.,])")


def number_style(text: str) -> NumberStyle | None:
    """What a document's own numbers say about `.`: "decimal" if some number can only be
    read with `.` as the decimal point (1,234.50),
    "thousands" if some number can only be read with `.` as the thousands separator
    (1.591.600 or 1.234,50), None if the document shows neither or both. A bare "9.99"
    says nothing, since a receipt that prints "TOTAL 60.000" may also print "Qty 4.00",
    and neither does "111,000": a receipt can print that beside "222.000"."""
    decimal = thousands = False
    for token in number_tokens(text):
        if token.count or not token.readings():
            continue
        digits = token.digits.rstrip(".,")
        decimal |= bool(_COMMA_THOUSANDS_TOKEN.fullmatch(digits))
        thousands |= bool(
            _DOT_THOUSANDS_TOKEN.fullmatch(digits) or _DOT_THOUSANDS_DECIMAL_TOKEN.fullmatch(digits)
        )
    if decimal == thousands:
        return None
    return "decimal" if decimal else "thousands"


_CURRENCY = r"(?:US\$|S\$|R\$|USD|EUR|GBP|JPY|CNY|INR|CHF|CAD|AUD|NZD|SGD|HKD|Rp\.?|RM|\$)"
# The candidate is intentionally broader than a supported amount: consume the WHOLE
# spelling, then reject it if necessary. Otherwise 1e6, .50 or 1,2,3 can yield a
# perfectly plausible number that was only a fragment of what the page said.
_NUMBER_TOKEN = re.compile(
    r"(?<![\w.,'/%+\-$])(?<!\d:)"
    r"(?P<open>\( *)?"
    r"(?P<sign>[+-] *)?"
    rf"(?P<currency>{_CURRENCY} *)?"
    r"(?P<inner_sign>[+-] *)?"
    r"(?P<count_prefix>x)?"
    r"(?P<number>(?:\d[\d.,']*|[.,]\d[\d.,']*)(?:[eE][+-]?\d+)?)"
    r"(?P<count_suffix>x)?"
    # A minus followed by another amount belongs to that amount. Do not steal
    # the prefix of the next receipt row ("Subtotal 18,182 - 15% DISC").
    rf"(?P<trailing_sign> *-(?! *(?:[\d.,]|{_CURRENCY})))?"
    r"(?P<percent> *[%\u2030])?"
    r"(?P<close> *\))?"
    r"(?![\w.,'/%+\-$]|:\d)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class NumberToken:
    """A whole numeric spelling and its original source span, including signs/units.

    Unsupported spellings still have a span: grounding must not remove their
    modifiers just to make a smaller quote match.
    """

    start: int
    end: int
    digits: str
    negative: bool
    percent: bool
    count: bool
    well_formed: bool

    def readings(self, style: NumberStyle | None = None) -> list[NumberReading]:
        if not self.well_formed or self.percent:
            return []
        readings = number_readings(self.digits, style)
        # A sentence's closing period/comma is not a decimal/thousands separator.
        if not readings and self.digits.endswith((".", ",")):
            readings = number_readings(self.digits[:-1], style)
        if self.negative:
            readings = [NumberReading(r.value.copy_negate(), r.places) for r in readings]
        return readings


def number_tokens(text: str) -> tuple[NumberToken, ...]:
    """Whole numeric tokens, never digits carved out of an identifier or exponent.

    Grounding's Unicode normalization handles minus signs, fullwidth characters and
    whitespace. Currency symbols share one lexical role; this does not convert units.
    The offset map preserves the exact original evidence and its bounding boxes.
    """
    normalized, offsets = normalize_with_map(text)
    # Grounding normalizes whitespace, but an amount's sign/unit must stay on
    # its line. Callers with page geometry restore those boundaries first.
    normalized = "".join(
        "\n" if c == " " and any(ch in "\r\n" for ch in text[offsets[i] : offsets[i + 1]]) else c
        for i, c in enumerate(normalized)
    )
    normalized = "".join(
        "$" if unicodedata.category(c) == "Sc" else "-" if c == "−" else c for c in normalized
    )
    tokens: list[NumberToken] = []
    for match in _NUMBER_TOKEN.finditer(normalized):
        open_, close = bool(match["open"]), bool(match["close"])
        signs = [
            match[name].strip() for name in ("sign", "inner_sign", "trailing_sign") if match[name]
        ]
        percent = bool(match["percent"])
        count = bool(match["count_prefix"] or match["count_suffix"])
        count_formed = not count or (
            not (match["count_prefix"] and match["count_suffix"])
            and not match["currency"]
            and not percent
        )
        start, end = offsets[match.start()], offsets[match.end() - 1] + 1
        # NFKC flattens superscripts and fractions. That is useful for finding
        # text, but 10² is not the amount 102 and ½ is neither 1 nor 2.
        decimal_glyphs = all(not c.isnumeric() or c.isdecimal() for c in text[start:end])
        tokens.append(
            NumberToken(
                start=start,
                end=end,
                digits=match["number"],
                negative="-" in signs or (open_ and close and not percent),
                percent=percent,
                count=count,
                well_formed=(
                    open_ == close
                    and len(signs) <= 1
                    and not (open_ and signs)
                    and decimal_glyphs
                    and count_formed
                ),
            )
        )
    return tuple(tokens)


def amount_readings(word: str, style: NumberStyle | None = None) -> list[NumberReading]:
    """Readings of a whole word that is an amount and nothing else: "$2,458.00", "Rp60.000",
    "(12.50)", "-3". A word with other letters or digits in it is not an amount."""
    stripped = word.strip().rstrip("*:;")
    tokens = number_tokens(stripped)
    if len(tokens) != 1:
        return []
    token = tokens[0]
    if token.count or token.start != 0 or token.end != len(stripped):
        return []
    return token.readings(style)


def same_value(a: NumberReading, b: NumberReading) -> bool:
    return a.value == b.value


# ---------------------------------------------------------------------------- dates

#: A day/month/year date with a numeric month, whatever separates its parts. The two
#: separators must be the same character, and a year with four digits cannot start inside a
#: longer number, so "2026-03-14" is not read as "26-03-14". Letter/underscore
#: boundaries also prevent a fragment of an identifier from becoming date evidence.
NUMERIC_DATE = re.compile(r"(?<![\w.\-/])(\d{1,2})([/.\-])(\d{1,2})\2(\d{4}|\d{2})(?![\w/\-]|\.\w)")
ISO_DATE = re.compile(r"(?<![\w.\-/])(\d{4})-(\d{2})-(\d{2})(?![\w/\-]|\.\w)")
WRITTEN_DATE = (
    re.compile(r"[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}"),
    re.compile(r"\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4}"),
)
_WRITTEN_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y")


def numeric_date_readings(match: re.Match[str]) -> dict[Literal["mdy", "dmy"], date]:
    first, _, second, year = match.groups()
    year_fmt = "%Y" if len(year) == 4 else "%y"
    readings: dict[Literal["mdy", "dmy"], date] = {}
    orders: tuple[tuple[Literal["mdy", "dmy"], str], ...] = (
        ("mdy", f"%m/%d/{year_fmt}"),
        ("dmy", f"%d/%m/{year_fmt}"),
    )
    for order, fmt in orders:
        try:
            readings[order] = datetime.strptime(f"{first}/{second}/{year}", fmt).date()
        except ValueError:
            continue
    return readings


def written_date(text: str) -> date | None:
    cleaned = re.sub(r"\.(?=\s)|(?<=[A-Za-z])\.$", "", text.strip())
    for fmt in _WRITTEN_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def dates_in(text: str) -> list[tuple[int, int, set[date]]]:
    """Every date written in `text`: (start, end, the days it can mean). A numeric date
    whose day and month are both 12 or under can mean two days; an ISO or written one
    means one."""
    found: list[tuple[int, int, set[date]]] = []
    for m in ISO_DATE.finditer(text):
        try:
            found.append(
                (m.start(), m.end(), {date(int(m.group(1)), int(m.group(2)), int(m.group(3)))})
            )
        except ValueError:
            continue
    for m in NUMERIC_DATE.finditer(text):
        readings = set(numeric_date_readings(m).values())
        if readings:
            found.append((m.start(), m.end(), readings))
    for pattern in WRITTEN_DATE:
        for m in pattern.finditer(text):
            d = written_date(m.group(0))
            if d is not None:
                found.append((m.start(), m.end(), {d}))
    return sorted(found)


def whole_date(text: str) -> set[date] | None:
    """The days `text` means if it is a date and nothing else ("25/12/2018", "2018-12-25",
    "25 December 2018"); None if it carries anything besides the date."""
    stripped = text.strip()
    for start, end, days in dates_in(stripped):
        if start == 0 and end == len(stripped):
            return days
    return None
