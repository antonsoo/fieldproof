"""Date evidence cannot legitimize a negated, ambiguous or alternative claim."""

from datetime import date

import pytest

from fieldproof.schemas import Evidenced
from fieldproof.schemas.invoice import Invoice
from fieldproof.verify import check_date, parse_date, parse_iso_date
from fieldproof.verify.cross_field import audit_invoice


@pytest.mark.parametrize(
    "value",
    [
        "not 2026-03-04",
        "2026-03-04 or 2026-04-03",
        "Issued: 2026-03-04",
        "03/04/2026",
        "March 4, 2026",
        "2026-3-4",
        "20260304",
        "2026-W10-3",
        "2026-03-04T00:00:00",
        " 2026-03-04",
        "2026-03-04\n",
        "２０２６-０３-０４",
        "2026-02-29",
        "0000-03-04",
        "2026-13-04",
    ],
)
def test_claim_requires_one_calendar_valid_iso_date(value: str) -> None:
    assert parse_iso_date(value) is None
    for convention in (None, "mdy", "dmy"):
        result = check_date(value, "Issue date: 2026-03-04", date_order=convention)
        assert not result.supported
        assert "YYYY-MM-DD" in result.reason


def test_claim_calendar_validity_matches_independent_date_constructor() -> None:
    for year in (1900, 2000, 2024, 2025):
        for month in range(14):
            for day in range(33):
                raw = f"{year:04d}-{month:02d}-{day:02d}"
                try:
                    expected = date(year, month, day)
                except ValueError:
                    expected = None
                assert parse_iso_date(raw) == expected


def test_flexible_evidence_reading_remains_available() -> None:
    for quote in ("March 4, 2026", "Issue date: 2026-03-04", "Issued 4 March 2026"):
        assert parse_date(quote) == date(2026, 3, 4)
        assert check_date("2026-03-04", quote).supported
    assert check_date("2026-03-04", "04/03/2026", date_order="dmy").supported
    assert check_date("2026-03-04", "03/04/2026", date_order="mdy").supported
    assert not check_date("2026-03-04", "03/04/2026").supported


@pytest.mark.parametrize("bad_field", ["issue_date", "due_date"])
def test_chronology_is_not_checked_when_one_claim_is_not_a_date(bad_field: str) -> None:
    values = {"issue_date": "2026-03-04", "due_date": "2026-03-05"}
    values[bad_field] = "not " + values[bad_field]
    invoice = Invoice(
        vendor_name=Evidenced(value="Example"),
        invoice_number=Evidenced(value="DATE-001"),
        issue_date=Evidenced(value=values["issue_date"]),
        due_date=Evidenced(value=values["due_date"]),
        total=Evidenced(value=10.0),
    )
    check = audit_invoice(invoice)[-1]
    assert check.status == "not_checked"
    assert check.operands == values
    assert "YYYY-MM-DD" in check.message
