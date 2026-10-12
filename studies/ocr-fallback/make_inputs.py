"""Rasterize the repository's synthetic examples; no model or scanner is involved."""

from __future__ import annotations

import hashlib
import io
import json
from contextlib import closing
from pathlib import Path

import pypdfium2 as pdfium
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from fieldproof.document.loader import EmptyDocumentError, load_pdf
from fieldproof.document.render import render_page_png

STUDY = Path(__file__).resolve().parent
ROOT = STUDY.parents[1]


def main() -> None:
    inputs = STUDY / "inputs"
    inputs.mkdir(exist_ok=True)
    manifest = []
    for name in ("invoice", "receipt", "contract"):
        source = ROOT / "examples" / f"{name}.pdf"
        output = inputs / f"scanned-{name}.pdf"
        with closing(pdfium.PdfDocument(source)) as pdf:
            canvas = Canvas(str(output), invariant=1)
            for number in range(1, len(pdf) + 1):
                with closing(pdf[number - 1]) as page:
                    width, height = page.get_size()
                canvas.setPageSize((width, height))
                raster = render_page_png(source, number, scale=2)
                canvas.drawImage(ImageReader(io.BytesIO(raster)), 0, 0, width, height)
                canvas.showPage()
            canvas.save()
        try:
            load_pdf(output)
        except EmptyDocumentError:
            pass
        else:
            raise AssertionError("rasterized PDF unexpectedly has extractable text")
        manifest.append(
            {
                "path": output.name,
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "source": f"examples/{name}.pdf",
                "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        )

    # Preserve a blank first page: field coordinates must continue to refer to page 2.
    canvas = Canvas(str(inputs / "blank-then-invoice.pdf"), pagesize=(612, 792), invariant=1)
    canvas.showPage()
    raster = render_page_png(ROOT / "examples/invoice.pdf", 1, scale=2)
    canvas.drawImage(ImageReader(io.BytesIO(raster)), 0, 0, 612, 792)
    canvas.save()
    canvas = Canvas(str(inputs / "blank.pdf"), pagesize=(612, 792), invariant=1)
    canvas.showPage()
    canvas.save()
    for name in ("blank-then-invoice.pdf", "blank.pdf"):
        path = inputs / name
        manifest.append(
            {
                "path": name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "source": "constructed blank page; invoice raster from examples/invoice.pdf",
            }
        )
    (STUDY / "inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {len(manifest)} controlled PDF inputs")


if __name__ == "__main__":
    main()
