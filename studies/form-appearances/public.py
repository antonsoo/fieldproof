"""Replay two pinned producer documents; inspect originals and one invented fill.

Requires pypdf==6.21.1 in addition to the project's development dependencies.
The upstream PDFs and their renders are CC BY-SA 4.0; see NOTICE.md.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
from contextlib import closing
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageChops
from pypdf import PdfReader, PdfWriter
from pypdf import __version__ as pypdf_version
from pypdfium2 import raw

from fieldproof.document.render import render_page_png

REVISION = "02b8203bf416db3dbdb03438bc8278dfcb0555f3"
FILES = ("012-libreoffice-form/libreoffice-form.pdf", "010-pdflatex-forms/pdflatex-forms.pdf")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--ocr", action="store_true", help="also recognize Poppler and review pixels"
    )
    args = parser.parse_args()
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=args.checkout, text=True
    ).strip()
    assert revision == REVISION
    subprocess.run(
        ["git", "diff", "--exit-code", "HEAD", "--", *FILES],
        cwd=args.checkout,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for relative in FILES:
        original = (args.checkout / relative).read_bytes()
        variants = [("original", original)]
        if relative.startswith("010-"):
            writer = PdfWriter(clone_from=io.BytesIO(original))
            writer.update_page_form_field_values(
                writer.pages[0], {"Name": "Example Form"}, auto_regenerate=False
            )
            stream = io.BytesIO()
            writer.write(stream)
            variants.append(("invented-fill", stream.getvalue()))
        for variant, source in variants:
            name = f"{Path(relative).stem}-{variant}"
            destination = args.output / f"{name}.pdf"
            destination.write_bytes(source)
            reader = PdfReader(io.BytesIO(source))
            fields = {
                key: {"type": value.get("/FT"), "value": value.get("/V")}
                for key, value in reader.get_fields().items()
            }
            item = {
                "source_path": relative,
                "source_sha256": digest(original),
                "variant": variant,
                "input_sha256": digest(source),
                "fields": fields,
                "producer": reader.metadata.producer,
                "pages": [],
            }
            with closing(pdfium.PdfDocument(source)) as native:
                native.init_forms(config=raw.FPDF_FORMFILLINFO(version=2, xfa_disabled=True))
                for index in range(len(native)):
                    stem = f"{name}-{index + 1}"
                    review = render_page_png(source, index + 1)
                    review_path = args.output / f"{stem}.review.png"
                    review_path.write_bytes(review)
                    with (
                        closing(native[index]) as page,
                        closing(page.render(scale=2)) as bitmap,
                        bitmap.to_pil() as expected,
                        Image.open(io.BytesIO(review)) as actual,
                        ImageChops.difference(
                            actual.convert("RGB"), expected.convert("RGB")
                        ) as delta,
                    ):
                        page_result = {
                            "number": index + 1,
                            "review_sha256": digest(review),
                            "matches_form_renderer": delta.getbbox() is None,
                        }
                    if args.ocr:
                        poppler_base = args.output / f"{stem}.poppler"
                        subprocess.run(
                            [
                                "pdftoppm",
                                "-r",
                                "144",
                                "-f",
                                str(index + 1),
                                "-l",
                                str(index + 1),
                                "-singlefile",
                                "-png",
                                str(destination),
                                str(poppler_base),
                            ],
                            check=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                        )
                        for label, image_path in (
                            ("review", review_path),
                            ("poppler", poppler_base.with_suffix(".poppler.png")),
                        ):
                            text = subprocess.check_output(
                                ["tesseract", str(image_path), "stdout", "--psm", "11"],
                                stderr=subprocess.PIPE,
                                text=True,
                            )
                            page_result[f"{label}_ocr"] = text
                    item["pages"].append(page_result)
            assert (args.checkout / relative).read_bytes() == original
            results.append(item)
    receipt = {
        "upstream": "https://github.com/py-pdf/sample-files",
        "revision": revision,
        "license": "CC BY-SA 4.0",
        "pypdf": pypdf_version,
        "cases": results,
    }
    (args.output / "public.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                "cases": len(results),
                "pages": sum(len(c["pages"]) for c in results),
                "mismatches": sum(
                    not p["matches_form_renderer"] for c in results for p in c["pages"]
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
