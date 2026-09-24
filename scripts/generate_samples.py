#!/usr/bin/env python3
"""Generate the synthetic sample documents used in tests, the CLI examples,
and the static Pages demo.

Every document here is synthetic - invented for this repository, not scanned
from a real business record - and is labelled as such wherever it's shown.
Each has a deliberately different layout (letterhead invoice, narrow
thermal-receipt strip, formal multi-page contract) so grounding and the
review UI are exercised against more than one document shape.

Run: `uv run python scripts/generate_samples.py` (writes into examples/).
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.pdfgen.canvas import Canvas

OUT_DIR = Path(__file__).resolve().parent.parent / "examples"


def build_invoice() -> None:
    path = OUT_DIR / "invoice.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 20)
    c.drawString(0.75 * inch, height - 0.9 * inch, "Northwind Freight & Supply Co.")
    c.setFont("Helvetica", 9)
    c.drawString(0.75 * inch, height - 1.1 * inch, "4821 Harbor Industrial Way, Oakland, CA 94607")
    c.drawString(0.75 * inch, height - 1.25 * inch, "billing@northwindfreight.example")

    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(width - 0.75 * inch, height - 0.9 * inch, "INVOICE")
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 0.75 * inch, height - 1.15 * inch, "Invoice Number: NW-20260214")
    c.drawRightString(width - 0.75 * inch, height - 1.32 * inch, "Issue Date: February 14, 2026")
    c.drawRightString(width - 0.75 * inch, height - 1.49 * inch, "Due Date: March 16, 2026")

    c.line(0.75 * inch, height - 1.7 * inch, width - 0.75 * inch, height - 1.7 * inch)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(0.75 * inch, height - 1.95 * inch, "Bill To:")
    c.setFont("Helvetica", 10)
    c.drawString(0.75 * inch, height - 2.12 * inch, "Cascade Retail Group")
    c.drawString(0.75 * inch, height - 2.28 * inch, "1900 Pike Street, Seattle, WA 98101")

    table_top = height - 2.7 * inch
    c.setFont("Helvetica-Bold", 10)
    c.drawString(0.75 * inch, table_top, "Description")
    c.drawString(4.3 * inch, table_top, "Qty")
    c.drawString(4.9 * inch, table_top, "Unit Price")
    c.drawRightString(width - 0.75 * inch, table_top, "Amount")
    c.line(0.75 * inch, table_top - 0.08 * inch, width - 0.75 * inch, table_top - 0.08 * inch)

    rows = [
        ("Pallet freight - Oakland to Seattle", "12", "145.00", "1,740.00"),
        ("Fuel surcharge", "1", "210.50", "210.50"),
        ("Liftgate delivery service", "3", "65.00", "195.00"),
        ("Warehouse handling fee", "1", "312.50", "312.50"),
    ]
    c.setFont("Helvetica", 10)
    y = table_top - 0.3 * inch
    for desc, qty, unit_price, amount in rows:
        c.drawString(0.75 * inch, y, desc)
        c.drawString(4.3 * inch, y, qty)
        c.drawString(4.9 * inch, y, unit_price)
        c.drawRightString(width - 0.75 * inch, y, amount)
        y -= 0.22 * inch

    y -= 0.1 * inch
    c.line(3.8 * inch, y, width - 0.75 * inch, y)
    y -= 0.25 * inch
    c.setFont("Helvetica", 10)
    c.drawString(3.8 * inch, y, "Subtotal")
    c.drawRightString(width - 0.75 * inch, y, "$2,458.00")
    y -= 0.22 * inch
    c.drawString(3.8 * inch, y, "Tax (8.5%)")
    c.drawRightString(width - 0.75 * inch, y, "$208.93")
    y -= 0.26 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(3.8 * inch, y, "Total Due")
    c.drawRightString(width - 0.75 * inch, y, "$2,666.93")

    y -= 0.5 * inch
    c.setFont("Helvetica", 9)
    c.drawString(0.75 * inch, y, "Payment Terms: Net 30. Remit payment by wire or check to the address above.")

    c.showPage()
    c.save()
    print(f"wrote {path}")


def build_receipt() -> None:
    path = OUT_DIR / "receipt.pdf"
    # Narrow page, mimicking a thermal POS receipt strip.
    page_size = (3.2 * inch, 6.5 * inch)
    c = canvas.Canvas(str(path), pagesize=page_size)
    width, height = page_size

    def center(text: str, y: float, font: str = "Helvetica", size: int = 9) -> None:
        c.setFont(font, size)
        c.drawCentredString(width / 2, y, text)

    y = height - 0.35 * inch
    center("Blue Heron Coffee Roasters", y, "Helvetica-Bold", 11)
    y -= 0.2 * inch
    center("118 Alder St, Portland, OR 97204", y)
    y -= 0.15 * inch
    center("(503) 555-0148", y)
    y -= 0.3 * inch
    c.line(0.15 * inch, y, width - 0.15 * inch, y)
    y -= 0.22 * inch
    center("Transaction Date: 03/14/2026 09:41 AM", y)
    y -= 0.2 * inch
    center("Register 2  -  Cashier: J.M.", y)
    y -= 0.3 * inch
    c.line(0.15 * inch, y, width - 0.15 * inch, y)
    y -= 0.25 * inch

    items = [
        ("Large Pour-Over", "1", "5.25"),
        ("Almond Croissant", "2", "4.50"),
        ("Cold Brew 16oz", "1", "4.75"),
        ("Bag of Beans - Ethiopia", "1", "17.00"),
    ]
    c.setFont("Helvetica", 8)
    for desc, qty, price in items:
        c.drawString(0.15 * inch, y, f"{desc} x{qty}")
        c.drawRightString(width - 0.15 * inch, y, f"${price}")
        y -= 0.18 * inch

    y -= 0.1 * inch
    c.line(0.15 * inch, y, width - 0.15 * inch, y)
    y -= 0.2 * inch
    c.setFont("Helvetica", 9)
    # Prices above are per unit, so the subtotal is their simple sum (this
    # receipt doesn't print a per-line total column) - 5.25 + 4.50 + 4.75 +
    # 17.00 = 31.50, and the fixture's line-item amounts match this exactly.
    c.drawString(0.15 * inch, y, "Subtotal")
    c.drawRightString(width - 0.15 * inch, y, "$31.50")
    y -= 0.18 * inch
    c.drawString(0.15 * inch, y, "Tax")
    c.drawRightString(width - 0.15 * inch, y, "$2.84")
    y -= 0.2 * inch
    c.setFont("Helvetica-Bold", 10)
    c.drawString(0.15 * inch, y, "Total")
    c.drawRightString(width - 0.15 * inch, y, "$34.34")
    y -= 0.3 * inch
    center("Payment Method: Visa ending 4471", y, size=8)
    y -= 0.25 * inch
    center("Thank you for stopping by!", y, size=8)

    c.showPage()
    c.save()
    print(f"wrote {path}")


def _contract_paragraph(c: Canvas, text: str, x: float, y: float, max_width: float, size: int = 9) -> float:
    """Very small manual word-wrap - reportlab has no built-in flowed text on
    a bare canvas, and pulling in Platypus for three paragraphs isn't worth
    the extra dependency surface for a fixture generator."""
    c.setFont("Helvetica", size)
    words = text.split()
    line = ""
    for word in words:
        trial = f"{line} {word}".strip()
        if c.stringWidth(trial, "Helvetica", size) > max_width:
            c.drawString(x, y, line)
            y -= size * 1.35
            line = word
        else:
            line = trial
    if line:
        c.drawString(x, y, line)
        y -= size * 1.35
    return y


def build_contract() -> None:
    path = OUT_DIR / "contract.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    margin = 1.0 * inch
    max_width = width - 2 * margin

    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, height - margin, "MASTER SERVICES AGREEMENT")
    c.setFont("Helvetica", 9)
    y = height - margin - 0.35 * inch
    y = _contract_paragraph(
        c,
        "This Master Services Agreement (“Agreement”) is entered into as of April 1, 2026 "
        "(the “Effective Date”) by and between Harborline Analytics, Inc., a Delaware "
        "corporation (“Provider”), and Meridian Health Systems LLC, an Oregon limited "
        "liability company (“Client”).",
        margin,
        y,
        max_width,
    )
    y -= 0.15 * inch

    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "1. Term")
    y -= 0.2 * inch
    y = _contract_paragraph(
        c,
        "This Agreement shall commence on the Effective Date and shall continue for an initial "
        "term of 24 months, unless earlier terminated in accordance with Section 4.",
        margin,
        y,
        max_width,
    )
    y -= 0.15 * inch

    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "2. Fees")
    y -= 0.2 * inch
    y = _contract_paragraph(
        c,
        "Client shall pay Provider a total contract value of $186,000.00, invoiced quarterly in "
        "equal installments, for the services described in Exhibit A.",
        margin,
        y,
        max_width,
    )
    y -= 0.15 * inch

    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "3. Governing Law")
    y -= 0.2 * inch
    y = _contract_paragraph(
        c,
        "This Agreement shall be governed by and construed in accordance with the laws of the "
        "State of Delaware, without regard to its conflict of laws principles.",
        margin,
        y,
        max_width,
    )
    y -= 0.15 * inch

    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "4. Termination")
    y -= 0.2 * inch
    y = _contract_paragraph(
        c,
        "Either party may terminate this Agreement for convenience upon sixty (60) days' prior "
        "written notice to the other party.",
        margin,
        y,
        max_width,
    )

    c.showPage()

    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, height - margin, "5. Key Obligations")
    y = height - margin - 0.25 * inch
    obligations = [
        "Provider shall maintain 99.5% uptime for all hosted services described in Exhibit A.",
        "Provider shall deliver a security incident report within 24 hours of discovery.",
        "Client shall designate a single point of contact for change requests.",
    ]
    for item in obligations:
        y = _contract_paragraph(c, f"- {item}", margin, y, max_width)
        y -= 0.05 * inch

    c.showPage()
    c.save()
    print(f"wrote {path}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    build_invoice()
    build_receipt()
    build_contract()


if __name__ == "__main__":
    main()
