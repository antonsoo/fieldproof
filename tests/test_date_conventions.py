"""Date-shaped references must not lend authority to an ambiguous issue date."""

from __future__ import annotations

from datetime import date
from io import BytesIO

from pydantic import BaseModel
from reportlab.pdfgen.canvas import Canvas

from fieldproof.document.loader import load_pdf
from fieldproof.schemas import Evidenced
from fieldproof.verify.engine import FieldStatus, verify
from fieldproof.verify.value_checks import check_date, numeric_date_order


class DateClaim(BaseModel):
    issue_date: Evidenced[str]


def test_convention_tokens_match_calendar_validity_not_component_ranges() -> None:
    # Independent date constructor oracle covers impossible days/months and
    # Gregorian century/leap-year boundaries, not the parser's format strings.
    for year in (1900, 2000, 2024, 2025):
        for first in range(33):
            for second in range(33):
                valid = set()
                for order, month, day in (("mdy", first, second), ("dmy", second, first)):
                    try:
                        date(year, month, day)
                        valid.add(order)
                    except ValueError:
                        pass
                expected = next(iter(valid)) if len(valid) == 1 else None
                token = f"{first:02}/{second:02}/{year}"
                assert numeric_date_order(f"Date: {token}.") == expected, token


def test_identifier_fragments_do_not_disambiguate_other_dates() -> None:
    for reference in (
        "ABC14/03/2026",
        "14/03/2026XYZ",
        "ref_14/03/2026",
        "ref-14/03/2026",
        "14/03/2026-XYZ",
        "14/03/2026/99",
        "14/03/2026.7",
    ):
        assert numeric_date_order(f"Issue 03/04/2026; Reference: {reference}") is None
    assert numeric_date_order("Date:14/03/2026") == "dmy"
    assert numeric_date_order("Date (14/03/2026).") == "dmy"
    assert numeric_date_order("14/03/2026 and 03/14/2026") is None
    assert numeric_date_order("03/14/2026 and 99/01/2026") == "mdy"


def test_actual_pdf_reference_cannot_override_month_first_default() -> None:
    pdf = BytesIO()
    canvas = Canvas(pdf, invariant=True)
    canvas.drawString(40, 720, "Issue Date: 03/04/2026")
    canvas.drawString(40, 690, "Reference: 99/01/2026")
    canvas.save()
    document = load_pdf(pdf.getvalue())
    for value, expected in (
        ("2026-03-04", FieldStatus.VERIFIED),
        ("2026-04-03", FieldStatus.NEEDS_REVIEW),
    ):
        claim = DateClaim(issue_date=Evidenced(value=value, evidence=["03/04/2026"], page=1))
        report = verify(claim, document, default_date_order="mdy")
        result = report.fields[0]
        assert result.status is expected
        assert result.page == 1 and result.rects
        assert result.matched_text == "03/04/2026"
        # Without a supplied convention neither reading has sufficient support.
        assert verify(claim, document).fields[0].status is FieldStatus.NEEDS_REVIEW


def test_date_parser_fallback_cannot_reaccept_rejected_identifier_fragments() -> None:
    for quote in (
        "ABC03/04/2026",
        "03/04/2026XYZ",
        "ref_03/04/2026",
        "ref-03/04/2026",
        "03/04/2026-XYZ",
        "03/04/2026/99",
        "03/04/2026.7",
        "ABC2026-04-03XYZ",
        "2026-04-03/99",
        "2026-04-03.7",
    ):
        for default in (None, "mdy", "dmy"):
            for value in ("2026-03-04", "2026-04-03"):
                assert not check_date(value, f"Reference: {quote}", date_order=default).supported
    assert check_date("2026-03-04", "Date:03/04/2026.", date_order="mdy").supported


def test_invalid_iso_in_same_quote_cannot_bypass_numeric_ambiguity() -> None:
    for iso in ("2026-99-99", "2026-02-29", "ABC2026-99-99XYZ"):
        quote = f"Issue: 03/04/2026; reference: {iso}"
        for value in ("2026-03-04", "2026-04-03"):
            assert not check_date(value, quote).supported
            assert check_date(value, quote, date_order="mdy").supported == (value == "2026-03-04")
            assert check_date(value, quote, date_order="dmy").supported == (value == "2026-04-03")
    assert check_date("2026-04-03", "Date:2026-04-03.").supported
