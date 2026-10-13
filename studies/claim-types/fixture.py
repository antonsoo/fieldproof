"""Generate a labelled synthetic PDF with unrelated and positive-control quotes."""

from pathlib import Path
from reportlab.pdfgen.canvas import Canvas

canvas = Canvas(str(Path(__file__).with_name("claims.pdf")), pagesize=(612, 792), invariant=True)
canvas.setTitle("Synthetic claim value type controls")
for index, line in enumerate(
    [
        "SYNTHETIC - claim value type controls",
        "Example Works",
        "13",
        "Approval: yes",
        "May 1, 2026",
        "Alpha 10.00",
        "Beta 10.00",
    ]
):
    canvas.drawString(50, 750 - 30 * index, line)
canvas.save()
