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
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

NumberStyle = Literal["decimal", "thousands"]

#: What a token of digits and separators looks like. Currency symbols, letters and a
#: percent sign are stripped by the caller; a token is only the number.
_COMMA_THOUSANDS = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
_DOT_THOUSANDS_MANY = re.compile(r"^\d{1,3}(?:\.\d{3}){2,}(?:,\d{1,2})?$")
_DOT_THOUSANDS_ONE = re.compile(r"^[1-9]\d{0,2}\.\d{3}$")
_DOT_THOUSANDS_COMMA_DECIMAL = re.compile(r"^\d{1,3}(?:\.\d{3})+,\d{1,2}$")
_COMMA_DECIMAL = re.compile(r"^\d+,\d{1,2}$")
_PLAIN = re.compile(r"^\d+(?:\.\d+)?$")


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
    if token.count(",") and not token.count("."):
        try:
            return [NumberReading(Decimal(token.replace(",", "")), 0)]
        except InvalidOperation:
            return []
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
    decimal = bool(_COMMA_THOUSANDS_TOKEN.search(text))
    thousands = bool(_DOT_THOUSANDS_TOKEN.search(text) or _DOT_THOUSANDS_DECIMAL_TOKEN.search(text))
    if decimal == thousands:
        return None
    return "decimal" if decimal else "thousands"


_AMOUNT_WORD = re.compile(
    r"^(?:[$\u20ac\u00a3\u00a5]|Rp\.?|RM|US\$|S\$)?(\(?)(-?)(\d[\d.,]*\d|\d)(\)?)[*:;,.]?$"
)


def amount_readings(word: str, style: NumberStyle | None = None) -> list[NumberReading]:
    """Readings of a whole word that is an amount and nothing else: "$2,458.00", "Rp60.000",
    "(12.50)", "-3". A word with other letters or digits in it is not an amount."""
    m = _AMOUNT_WORD.match(word)
    if not m:
        return []
    open_, sign, digits, close = m.groups()
    readings = number_readings(digits, style)
    if sign or (open_ and close):
        readings = [NumberReading(-r.value, r.places) for r in readings]
    return readings


def same_value(a: NumberReading, b: NumberReading) -> bool:
    return a.value == b.value


# ---------------------------------------------------------------------------- dates

#: A day/month/year date with a numeric month, whatever separates its parts. The two
#: separators must be the same character, and a year with four digits cannot start inside a
#: longer number, so "2026-03-14" is not read as "26-03-14".
NUMERIC_DATE = re.compile(r"(?<![\d.\-/])(\d{1,2})([/.\-])(\d{1,2})\2(\d{4}|\d{2})(?![\d])")
ISO_DATE = re.compile(r"(?<![\d.\-/])(\d{4})-(\d{2})-(\d{2})(?!\d)")
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
