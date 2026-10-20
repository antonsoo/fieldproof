"""Wrap the pinned CORD photograph without editing pixels. Needs pyarrow + ReportLab.

Use the Parquet cache downloaded by studies/cord-grounding, or pass --parquet.
This script verifies the source, native-text absence and embedded RGB pixels.
It never generates extraction claims or changes fixture.json.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import pyarrow.parquet as pq
import pypdfium2 as pdfium
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "examples/recorded/cord"


def digest(content):
    return hashlib.sha256(content).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads((DIRECTORY / "source.json").read_text())
    parquet = args.parquet or ROOT / "studies/cord-grounding/cache" / source["parquet"]["name"]
    assert digest(parquet.read_bytes()) == source["parquet"]["sha256"]
    row = pq.read_table(parquet).slice(source["row"], 1).to_pylist()[0]
    original = row["image"]["bytes"]
    assert digest(original) == source["imageSha256"]
    image = Image.open(io.BytesIO(original)).convert("RGB")
    assert digest(image.tobytes()) == source["imagePixelRgbSha256"]
    width, height = image.size
    target = io.BytesIO()
    pdf = canvas.Canvas(target, pagesize=(width / 2, height / 2), invariant=1)
    pdf.setTitle("CORD v2 test receipt 0: unmodified photo in an image-only PDF")
    pdf.setAuthor("CORD contributors / NAVER CLOVA")
    pdf.setSubject(
        "CC BY 4.0: https://creativecommons.org/licenses/by/4.0/ . Source: "
        "https://huggingface.co/datasets/naver-clova-ix/cord-v2/tree/"
        f"{source['dataset']['revision']} . Photo unchanged; "
        "PDF wrapper created for Fieldproof review."
    )
    pdf.drawImage(ImageReader(image), 0, 0, width=width / 2, height=height / 2)
    pdf.showPage()
    pdf.save()
    content = target.getvalue()
    with pdfium.PdfDocument(content) as document:
        page = document[0]
        assert page.get_textpage().get_text_range() == ""
        objects = list(page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE]))
        assert len(objects) == 1
        embedded = objects[0].get_bitmap().to_pil().convert("RGB")
        assert embedded.size == image.size and embedded.tobytes() == image.tobytes()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "cord-test-0000.pdf").write_bytes(content)
    # Keep the data license with any extracted photograph and annotations.
    (args.out / "cord-test-0000.png").write_bytes(original)
    (args.out / "ground-truth.json").write_text(
        json.dumps(json.loads(row["ground_truth"]), indent=2) + "\n"
    )
    receipt = {
        "parquetSha256": digest(parquet.read_bytes()),
        "imageSha256": digest(original),
        "pdfSha256": digest(content),
        "matchesRecordedPdf": content == (DIRECTORY / "cord-test-0000.pdf").read_bytes(),
        "embeddedPixelsExact": True,
        "nativeText": "",
    }
    (args.out / "preparation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
