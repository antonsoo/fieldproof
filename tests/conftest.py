from __future__ import annotations

import io
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _make_pdf(lines_per_page: list[list[str]]) -> bytes:
    """Render pages of left-aligned lines of text at fixed y-steps, using
    reportlab - a minimal, controllable PDF generator for tests. Not meant
    to look nice; just to produce a real text layer with known content."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for lines in lines_per_page:
        c.setFont("Helvetica", 11)
        y = 740
        for line in lines:
            c.drawString(72, y, line)
            y -= 20
        c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture
def simple_invoice_pdf_bytes() -> bytes:
    return _make_pdf(
        [
            [
                "Acme Corporation",
                "Invoice Number: INV-1001",
                "Issue Date: January 1, 2026",
                "Due Date: January 31, 2026",
                "Widget Assembly - Qty 2 - $50.00",
                "Subtotal: $100.00",
                "Tax: $10.00",
                "Total: $110.00",
                "Payment Terms: Net 30",
            ]
        ]
    )


@pytest.fixture
def simple_invoice_pdf_path(tmp_path: Path, simple_invoice_pdf_bytes: bytes) -> Path:
    path = tmp_path / "invoice.pdf"
    path.write_bytes(simple_invoice_pdf_bytes)
    return path


@pytest.fixture
def two_page_pdf_bytes() -> bytes:
    return _make_pdf(
        [
            ["Page one has the vendor name Contoso Ltd on it."],
            ["Page two has the invoice total of $4,250.00 written here."],
        ]
    )


@pytest.fixture
def hyphenated_pdf_bytes() -> bytes:
    # A single long word broken across two "lines" by a hyphen, the way a
    # justified-text renderer wraps it - the words extractor sees two
    # separate tokens ("reimburse-" and "ment") joined by our flattening.
    return _make_pdf(
        [["This clause covers employee reimburse-", "ment of travel expenses in full."]]
    )
