"""Regenerate the labelled synthetic PDF; requires the development ReportLab dependency."""
from pathlib import Path
from reportlab.pdfgen.canvas import Canvas

canvas = Canvas(str(Path(__file__).with_name('synthetic-containers.pdf')), pagesize=(612,792), invariant=True)
canvas.setTitle('Synthetic container-traversal controls')
for y, text in [(730,'SYNTHETIC - custom-schema container controls'), (680,'Alpha 10.00'),
                (650,'Beta 10.00'), (610,'Example Works')]:
    canvas.drawString(50, y, text)
canvas.save()
