"""Independent PDFium/Poppler rendering checks, with the alternate text omitted."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tempfile
from pathlib import Path

import pypdfium2 as pdfium
from generate import ROOT, text
from PIL import Image
from reportlab.pdfgen.canvas import Canvas


def pixels(path: Path, engine: str, work: Path) -> tuple[tuple[int, int], bytes]:
    if engine == "pdfium":
        with pdfium.PdfDocument(path) as document:
            page = document[0]
            bitmap = page.render(scale=1)
            image = bitmap.to_pil().convert("RGB")
            result = (image.size, image.tobytes())
            bitmap.close()
            page.close()
            return result
    prefix = work / "poppler"
    subprocess.run([
        "pdftoppm", "-r", "72", "-singlefile", "-png", str(path), str(prefix)
    ], check=True, capture_output=True)
    with Image.open(prefix.with_suffix(".png")) as image:
        rgb = image.convert("RGB")
        return rgb.size, rgb.tobytes()


def main() -> None:
    observations = []
    with tempfile.TemporaryDirectory(prefix="fieldproof-pixels-") as directory:
        work = Path(directory)
        for rotation in (0, 90, 180, 270):
            stream = io.BytesIO()
            pdf = Canvas(stream, pagesize=(612, 792), invariant=True)
            text(pdf, 40, 750, "Synthetic rendering-mode control")
            text(pdf, 40, 680, "Amount due: $100.00")
            pdf.save()
            reference = work / f"reference-{rotation}.pdf"
            with pdfium.PdfDocument(stream.getvalue()) as document:
                page = document[0]
                page.set_rotation(rotation)
                document.save(reference)
                page.close()
            for engine in ("pdfium", "poppler"):
                expected_size, expected_pixels = pixels(reference, engine, work)
                names = (
                    [f"mode-{mode}" for mode in (3, 7)] + [f"form-{mode}" for mode in (3, 7)]
                    if rotation == 0 else
                    [f"rotated-{rotation}-mode-{mode}" for mode in (3, 7)]
                )
                for name in names:
                    size, data = pixels(ROOT / "fixtures" / f"{name}.pdf", engine, work)
                    equal = size == expected_size and data == expected_pixels
                    observations.append({
                        "case": name, "engine": engine, "size": size,
                        "sha256_rgb": hashlib.sha256(data).hexdigest(),
                        "equal_to_pdf_without_alternate_text": equal,
                    })
                    assert equal, (name, engine)
    destination = ROOT / "results/pixels.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({"checks": observations}, indent=2) + "\n")
    print(f"{len(observations)} pixel-identical comparisons against omitted-text references")


if __name__ == "__main__":
    main()
