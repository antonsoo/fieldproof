from __future__ import annotations

import pytest

from fieldproof.document.loader import EmptyDocumentError, load_pdf
from fieldproof.document.render import page_pixel_size, render_page_png


def test_load_pdf_extracts_words_with_offsets(simple_invoice_pdf_bytes: bytes) -> None:
    doc = load_pdf(simple_invoice_pdf_bytes, label="invoice.pdf")

    assert doc.page_count == 1
    page = doc.pages[0]
    assert "Invoice Number: INV-1001" in page.text
    assert page.words, "expected extracted words with bounding boxes"

    for word in page.words:
        assert page.text[word.start : word.end] == word.text


def test_load_pdf_multi_page(two_page_pdf_bytes: bytes) -> None:
    doc = load_pdf(two_page_pdf_bytes)
    assert doc.page_count == 2
    assert "Contoso" in doc.pages[0].text
    assert "4,250.00" in doc.pages[1].text


def test_load_pdf_rejects_empty_document() -> None:
    import io

    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.showPage()  # a page with no text at all
    c.save()

    with pytest.raises(EmptyDocumentError):
        load_pdf(buf.getvalue())


def test_page_not_found_raises_index_error(simple_invoice_pdf_bytes: bytes) -> None:
    doc = load_pdf(simple_invoice_pdf_bytes)
    with pytest.raises(IndexError):
        doc.page(2)


def test_render_page_png_produces_valid_png(simple_invoice_pdf_bytes: bytes) -> None:
    png_bytes = render_page_png(simple_invoice_pdf_bytes, 1, scale=1.0)
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_page_pixel_size_matches_scale(simple_invoice_pdf_bytes: bytes) -> None:
    w1, h1 = page_pixel_size(simple_invoice_pdf_bytes, 1, scale=1.0)
    w2, h2 = page_pixel_size(simple_invoice_pdf_bytes, 1, scale=2.0)
    assert w2 == pytest.approx(w1 * 2, abs=1)
    assert h2 == pytest.approx(h1 * 2, abs=1)
