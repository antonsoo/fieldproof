"""Behaviour changed after grounding was measured on annotated receipts
(`studies/cord-grounding/`). Every page text here is a few words of a CORD v2 or SROIE
receipt, so each case is one that went wrong on a real document.

CORD v2: Park et al., "CORD: A Consolidated Receipt Dataset for Post-OCR Parsing",
Document Intelligence Workshop at NeurIPS 2019, CC BY 4.0. SROIE: ICDAR 2019."""

from __future__ import annotations

from fieldproof.document.model import BBox, Document, Page, Word
from fieldproof.ground.align import find_candidates, find_candidates_in_document
from fieldproof.ground.values import amount_readings, number_style
from fieldproof.schemas import Evidenced
from fieldproof.verify.engine import FieldStatus, verify
from fieldproof.verify.value_checks import check_date, check_number, check_string


def _page(text: str) -> Page:
    words: list[Word] = []
    offset = 0
    for token in text.split(" "):
        box = BBox(x0=float(offset), top=10.0, x1=float(offset + len(token)), bottom=20.0)
        words.append(Word(text=token, bbox=box, start=offset, end=offset + len(token)))
        offset += len(token) + 1
    return Page(number=1, width=600.0, height=800.0, text=text, words=words)


def _document(text: str) -> Document:
    return Document(source="receipt", pages=[_page(text)])


def test_a_value_is_not_supported_by_a_number_a_cent_away() -> None:
    # SROIE: a total of 9.00 was "verified" against a page that said 9.01.
    assert check_number(9.0, "TOTAL 9.00").supported
    assert not check_number(9.01, "TOTAL 9.00").supported
    assert check_number(9.9999, "TOTAL 10.00").supported  # rounding is still rounding


def test_dot_thousands_verify_neither_reading_until_something_says_which() -> None:
    # CORD (Indonesian receipts): "TOTAL 60.000" is sixty thousand rupiah. Both readings
    # used to pass, so a value a thousand times too small was verified 383 times in 409.
    for value in (60000.0, 60.0):
        unsettled = check_number(value, "TOTAL 60.000")
        assert not unsettled.supported
        assert "reads as 60 (a decimal point) or 60000 (a thousands separator)" in unsettled.reason
    assert check_number(60000.0, "TOTAL 60.000", number_style="thousands").supported
    assert not check_number(60.0, "TOTAL 60.000", number_style="thousands").supported
    assert check_number(60.0, "TOTAL 60.000", number_style="decimal").supported
    assert not check_number(60000.0, "TOTAL 60.000", number_style="decimal").supported
    # a number that reads one way is not held back by a neighbour that reads two
    assert check_number(60000.0, "TOTAL 60.000 60,000").supported
    # Tight spacing cannot establish whether this is a quantity plus price.
    assert not check_number(4.0, "4 60.000").supported
    assert check_number(4.0, "4\t60.000").supported
    assert check_number(0.125, "0.125").supported  # no thousands group starts with 0
    wrong = check_number(61.0, "TOTAL 60.000")
    assert not wrong.supported and "does not match" in wrong.reason
    assert number_style("Subtotal 1.591.600 TAX 5.455") == "thousands"
    assert number_style("TOTAL 1,234.50 CASH 60.000") == "decimal"
    assert number_style("3 111,000 222.000") is None  # CORD: one receipt, both conventions
    assert number_style("TOTAL 60.000 TAX 10.00 % Qty 4.00") is None
    assert number_style("TOTAL 60.000") is None


def test_amount_words_are_amounts_and_codes_are_not() -> None:
    assert [r.value for r in amount_readings("Rp60.000")] == [60, 60000]
    assert [r.value for r in amount_readings("(12.50)")] == [-12.5]
    assert amount_readings("TD01167104") == []
    assert amount_readings("8.5%") == []


def test_numeric_dates_with_dashes_and_dots() -> None:
    # SROIE writes dates 25/12/2018, 12-01-19, 23-01-2019.
    assert check_date("2019-01-23", "23-01-2019").supported
    assert check_date("2019-01-12", "12.01.19", date_order="dmy").supported
    assert not check_date("2019-01-22", "23-01-2019").supported
    ambiguous = check_date("2019-01-12", "12-01-19")
    assert not ambiguous.supported and "no other date" in ambiguous.reason


def test_a_changed_letter_is_not_the_name_on_the_page() -> None:
    evidence = "BOOK TA .K(TAMAN DAYA) SDN BHD"
    assert check_string("BOOK TA .K(TAMAN DAYA) SDN BHD", evidence).supported
    assert check_string("Book Ta K Taman Daya Sdn Bhd", evidence).supported  # case, punctuation
    assert check_string("TAMAN DAYA", evidence).supported  # words left off
    assert check_string("MR DIY", "MR D.I.Y. (JOHOR) SDN BHD").supported
    changed = check_string("BOOK TA .K(TAMAN DAYB) SDN BHD", evidence)
    assert not changed.supported and "letters or digits" in changed.reason


def test_a_quote_the_model_rewrote_as_a_number_is_found_by_value() -> None:
    page = _page("Subtotal 60.000 TAX 5.455 TOTAL 60.000")
    (match,) = find_candidates("5455", page)
    assert match.matched_text == "5.455" and match.by_value and match.is_strong
    assert not match.is_exact
    # the same quote does not find a different number, however alike it looks
    assert find_candidates("5545", page) == []
    assert [m.matched_text for m in find_candidates("60000", page)] == ["60.000", "60.000"]


def test_a_quote_the_model_rewrote_as_a_date_is_found_by_value() -> None:
    page = _page("DATE: 25/12/2018 8:13:39 PM CASHIER: MANIS")
    (match,) = find_candidates("2018-12-25", page)
    assert match.matched_text == "25/12/2018" and match.by_value
    assert find_candidates("2018-12-26", page) == []


def test_a_name_in_other_case_is_found_wherever_the_page_has_it() -> None:
    page = _page("Free Ice Tea 1 0 Tahu Telor Asin 1 17,000 Free Ice Tea 1 0")
    found = find_candidates("free ice tea", page)
    assert len(found) == 2  # two places: ambiguous, not silently the first
    assert all(m.is_strong and not m.is_exact for m in found)


def test_a_fuzzy_match_with_a_different_letter_is_never_strong() -> None:
    page = _page("INDAH GIFT & HOME DECO 27,JALAN DEDAP 13")
    (match,) = find_candidates("INDAH GIFT & HOME DECQ", page)
    assert match.score > 90 and match.letters_agree is False
    assert not match.is_strong


def test_fuzzy_numbers_keep_their_separators() -> None:
    # SROIE: a made-up total of 12.00 was verified against the time "12:00".
    page = _page("C02102772 9/2/2017 12:00 PM T03 TOTAL 362.50")
    candidates = find_candidates("12.00", page)
    assert candidates and all(not m.is_strong for m in candidates)


def test_engine_reports_a_letter_difference_for_a_misquoted_name() -> None:
    from pydantic import BaseModel

    class Name(BaseModel):
        merchant_name: Evidenced[str]

    document = _document("INDAH GIFT & HOME DECO 27,JALAN DEDAP 13,")
    quote = "INDAH GIFT & HOME DEC0"
    report = verify(Name(merchant_name=Evidenced(value=quote, evidence=[quote], page=1)), document)
    (field,) = report.fields
    assert field.status is FieldStatus.NEEDS_REVIEW
    assert "differs from it in letters or digits" in field.reasons[0]
    assert find_candidates_in_document(quote, document)


def test_a_minus_sign_is_part_of_the_number() -> None:
    # CORD: "Kembali -30,000" is change given back; a total of 30,000 is not on this page.
    page = _page("Total 20,000 Tendered 50,000 Kembali -30,000")
    assert not any(m.is_strong for m in find_candidates("30,000", page))
    assert [m.matched_text for m in find_candidates("-30,000", page)] == ["-30,000"]
    assert [m.matched_text for m in find_candidates("50,000", page)] == ["50,000"]


def _name_report(quote: str, value: str, page: str, **kw):
    from pydantic import BaseModel

    class Name(BaseModel):
        merchant_name: Evidenced[str]

    data = Name(merchant_name=Evidenced(value=value, evidence=[quote], page=1))
    (field,) = verify(data, _document(page), **kw).fields
    return field


def test_text_edit_tolerance_is_off_by_default_and_recorded_when_on() -> None:
    # An OCR-garbled page ("DECO" read as "DEC0"): the model copies the quote faithfully
    # and writes the repaired name as the value.
    page = "INDAH GIFT & HOME DEC0 27,JALAN DEDAP 13,"
    quote, value = "INDAH GIFT & HOME DEC0", "INDAH GIFT & HOME DECO"
    strict = _name_report(quote, value, page)
    assert strict.status is FieldStatus.NEEDS_REVIEW and not strict.notes
    tolerant = _name_report(quote, value, page, text_edit_tolerance=1)
    assert tolerant.status is FieldStatus.VERIFIED
    assert "by 1 letter" in tolerant.notes[0] and "text_edit_tolerance=1" in tolerant.notes[0]
    assert tolerant.to_dict()["notes"] == tolerant.notes
    assert "notes" not in strict.to_dict()


def test_text_edit_tolerance_has_limits() -> None:
    page = "INDAH GIFT & HOME DEC0 27,JALAN DEDAP 13,"
    # two letters off with a tolerance of one
    assert (
        _name_report(
            "INDAH GIFT & HOME DEC0", "INDAH GIFT & HOME DEQQ0", page, text_edit_tolerance=1
        ).status
        is FieldStatus.NEEDS_REVIEW
    )
    # a short string: one letter is a different company
    short = _name_report("SDN BHD", "SDM BHD", "TAN SDN BHD", text_edit_tolerance=1)
    assert short.status is FieldStatus.NEEDS_REVIEW
    # a made-up name that is not close to the page
    far = _name_report("ACME TRADING COMPANY", "ACME TRADING COMPANY", page, text_edit_tolerance=2)
    assert far.status is FieldStatus.UNSUPPORTED


def _amount_report(value: float, quote: str, page: str, **kw):
    from pydantic import BaseModel

    class Total(BaseModel):
        total: Evidenced[float]

    data = Total(total=Evidenced(value=value, evidence=[quote], page=1))
    (field,) = verify(data, _document(page), **kw).fields
    return field


def test_an_unsettled_amount_is_for_review_until_the_caller_says_how_to_read_it() -> None:
    page = "Nasi Goreng 1 25.000 TOTAL 60.000 CASH 100.000"
    for value in (60000.0, 60.0):
        field = _amount_report(value, "TOTAL 60.000", page)
        assert field.status is FieldStatus.NEEDS_REVIEW
        assert "settles which" in field.reasons[0]
    stated = {"default_number_style": "thousands"}
    assert _amount_report(60000.0, "TOTAL 60.000", page, **stated).status is FieldStatus.VERIFIED
    assert _amount_report(60.0, "TOTAL 60.000", page, **stated).status is FieldStatus.NEEDS_REVIEW
    # the quote a model rewrote as a plain number is held to the same reading
    assert _amount_report(60000.0, "60000", page, **stated).status is FieldStatus.VERIFIED
    assert _amount_report(60.0, "60", page, **stated).status is FieldStatus.NEEDS_REVIEW
    assert _amount_report(60.0, "60", page).status is FieldStatus.NEEDS_REVIEW


def test_a_document_that_settles_its_own_numbers_is_read_its_own_way() -> None:
    page = "Subtotal 1.591.600 TAX 5.455 TOTAL 60.000"
    assert _amount_report(60000.0, "TOTAL 60.000", page).status is FieldStatus.VERIFIED
    told_otherwise = _amount_report(60.0, "TOTAL 60.000", page, default_number_style="decimal")
    assert told_otherwise.status is FieldStatus.NEEDS_REVIEW
    assert "does not match 60000" in told_otherwise.reasons[0]


def test_default_date_order_reads_a_date_nothing_on_the_page_settles() -> None:
    from pydantic import BaseModel

    class Receipt(BaseModel):
        transaction_date: Evidenced[str]

    def status(value: str, page: str, **kw) -> FieldStatus:
        data = Receipt(transaction_date=Evidenced(value=value, evidence=["03/04/2019"], page=1))
        (field,) = verify(data, _document(page), **kw).fields
        return field.status

    page = "DATE: 03/04/2019 TOTAL 9.00"  # SROIE: Malaysian receipts write the day first
    assert status("2019-04-03", page) is FieldStatus.NEEDS_REVIEW
    assert status("2019-04-03", page, default_date_order="dmy") is FieldStatus.VERIFIED
    assert status("2019-03-04", page, default_date_order="dmy") is FieldStatus.NEEDS_REVIEW
    # another date on the page says month first: the default does not override it
    settled = "DATE: 03/04/2019 DUE 03/25/2019"
    assert status("2019-03-04", settled, default_date_order="dmy") is FieldStatus.VERIFIED


def test_a_mistyped_default_is_an_error() -> None:
    import pytest

    with pytest.raises(ValueError, match="default_number_style"):
        _amount_report(1.0, "1", "1", default_number_style="european")
    with pytest.raises(ValueError, match="default_date_order"):
        _amount_report(1.0, "1", "1", default_date_order="ymd")
