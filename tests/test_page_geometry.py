from __future__ import annotations

import io

import pypdfium2 as pdfium
import pytest
from PIL import Image, ImageChops
from reportlab.pdfgen import canvas

from fieldproof.document.loader import load_pdf
from fieldproof.document.render import page_pixel_size, render_page_png
from fieldproof.schemas import Evidenced
from fieldproof.schemas.invoice import Invoice
from fieldproof.verify.engine import FieldStatus, verify


def marked_pdf(*, rotation=0, crop=None, media=None, text_rotation=0, text="Marker"):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(612, 792))
    pdf.setFillColorRGB(1, 0, 0)
    pdf.rect(145, 575, 90, 40, fill=1, stroke=0)
    pdf.setFillColorRGB(0, 0, 0)
    if text_rotation:
        pdf.saveState()
        pdf.translate(200, 600)
        pdf.rotate(text_rotation)
        pdf.drawString(0, 0, text)
        pdf.restoreState()
    else:
        pdf.drawString(150, 600, text)
    pdf.drawString(20, 720, "HIDDEN")
    pdf.save()
    with pdfium.PdfDocument(buffer.getvalue()) as document:
        page = document[0]
        if media is not None:
            page.set_mediabox(*media)
        if crop is not None:
            page.set_cropbox(*crop)
        page.set_rotation(rotation)
        output = io.BytesIO()
        document.save(output)
        page.close()
    return output.getvalue()


# Absolute expected red marker positions in the PNG. These are specified from
# the authored PDF rectangle and visible canvas, independently of loader boxes.
CASES = [
    ("crop", 0, (400, 500), (45, 85, 135, 125)),
    ("crop", 90, (500, 400), (375, 45, 415, 135)),
    ("crop", 180, (400, 500), (265, 375, 355, 415)),
    ("crop", 270, (500, 400), (85, 265, 125, 355)),
    ("shift", 0, (612, 792), (95, 257, 185, 297)),
    ("shift", 90, (792, 612), (495, 95, 535, 185)),
    ("shift", 180, (612, 792), (427, 495, 517, 535)),
    ("shift", 270, (792, 612), (257, 427, 297, 517)),
    ("outside", 0, (612, 792), (145, 177, 235, 217)),
    ("outside", 90, (792, 612), (575, 145, 615, 235)),
    ("outside", 180, (612, 792), (377, 575, 467, 615)),
    ("outside", 270, (792, 612), (177, 377, 217, 467)),
    ("both", 0, (400, 500), (45, 85, 135, 125)),
    ("both", 90, (500, 400), (375, 45, 415, 135)),
    ("both", 180, (400, 500), (265, 375, 355, 415)),
    ("both", 270, (500, 400), (85, 265, 125, 355)),
]


@pytest.mark.parametrize("kind,rotation,size,marker", CASES)
def test_visible_page_frame_and_grounded_boxes_match_actual_png_pixels(
    kind, rotation, size, marker
):
    content = marked_pdf(
        rotation=rotation,
        crop=(100, 200, 500, 700)
        if kind in {"crop", "both"}
        else (-100, -100, 800, 1000)
        if kind == "outside"
        else None,
        media=(50, 80, 662, 872) if kind in {"shift", "both"} else None,
    )
    document = load_pdf(content)
    page = document.pages[0]
    image = Image.open(io.BytesIO(render_page_png(content, 1, scale=1))).convert("RGB")
    assert image.size == size
    assert (page.width, page.height) == size
    assert page_pixel_size(content, 1, scale=1) == size
    red, green, blue = image.split()
    red_mask = ImageChops.multiply(
        red.point(lambda v: 255 if v > 200 else 0),
        ImageChops.multiply(
            green.point(lambda v: 255 if v < 50 else 0),
            blue.point(lambda v: 255 if v < 50 else 0),
        ),
    )
    actual_marker = red_mask.getbbox()
    assert actual_marker is not None
    assert all(
        abs(actual - expected) <= 1 for actual, expected in zip(actual_marker, marker, strict=True)
    )
    assert "Marker" in page.text  # Rotation must not reverse its letters into "rekraM".
    if kind in {"crop", "shift", "both"}:
        assert "HIDDEN" not in page.text
    data = Invoice(
        vendor_name=Evidenced[str](value="Marker", evidence=["Marker"]),
        invoice_number=Evidenced[str](value="M1", evidence=[]),
        issue_date=Evidenced[str](value="2026-10-04", evidence=[]),
        total=Evidenced[float](value=1.0, evidence=[]),
    )
    field = next(field for field in verify(data, document).fields if field.path == "vendor_name")
    assert field.status == FieldStatus.VERIFIED
    assert field.page == 1
    assert field.rects
    for box in field.rects:
        assert marker[0] <= box["x0"] < box["x1"] <= marker[2]
        assert marker[1] <= box["top"] < box["bottom"] <= marker[3]


def test_fractional_canvas_pixel_size_uses_the_renderers_ceiling():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(200.25, 300.25))
    pdf.drawString(20, 100, "Fractional page")
    pdf.save()
    content = buffer.getvalue()
    for scale, expected in [(1, (201, 301)), (2, (401, 601))]:
        assert page_pixel_size(content, 1, scale=scale) == expected
        assert Image.open(io.BytesIO(render_page_png(content, 1, scale=scale))).size == expected


def test_fully_cropped_out_text_is_not_usable_evidence():
    content = marked_pdf(crop=(300, 200, 500, 700))
    from fieldproof.document.loader import EmptyDocumentError

    with pytest.raises(EmptyDocumentError):
        load_pdf(content)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_counter_rotated_text_keeps_logical_letters_and_decimal_numbers(rotation):
    content = marked_pdf(
        rotation=rotation,
        crop=(100, 200, 500, 700),
        text_rotation=-rotation,
        text="Marker 123.45",
    )
    document = load_pdf(content)
    assert document.pages[0].text == "Marker 123.45"
    for word in document.pages[0].words:
        assert 0 <= word.bbox.x0 <= word.bbox.x1 <= document.pages[0].width
        assert 0 <= word.bbox.top <= word.bbox.bottom <= document.pages[0].height


def test_clipped_characters_cannot_supply_the_whole_original_quote():
    content = marked_pdf(crop=(160, 200, 500, 700))
    page = load_pdf(content).pages[0]
    assert page.words
    assert "Marker" not in page.text
