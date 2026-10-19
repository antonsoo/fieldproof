"""Retain actual review pixels, native paint checks and direct PDFium controls."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageChops
from pydantic import BaseModel
from pypdfium2 import raw
from pypdfium2.version import PDFIUM_INFO, PYPDFIUM_INFO

from fieldproof.document.loader import EmptyDocumentError, load_pdf
from fieldproof.document.model import document_from_dict
from fieldproof.document.render import render_page_png
from fieldproof.schemas import Evidenced
from fieldproof.verify import verify

HERE = Path(__file__).resolve().parent


class Amount(BaseModel):
    total: Evidenced[float]


def control(source: bytes, forms: bool) -> Image.Image:
    with closing(pdfium.PdfDocument(source)) as pdf:
        if forms:
            pdf.init_forms(config=raw.FPDF_FORMFILLINFO(version=2, xfa_disabled=True))
        with (
            closing(pdf[0]) as page,
            closing(page.render(scale=2)) as bitmap,
            bitmap.to_pil() as image,
        ):
            return image.convert("RGB")


def replay(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    cases = json.loads((HERE / "cases.json").read_text())
    results = []
    for case in cases:
        path = HERE / "fixtures" / f"{case['id']}.pdf"
        source = path.read_bytes()
        assert hashlib.sha256(source).hexdigest() == case["sha256"]
        item = {"id": case["id"], "source_sha256": case["sha256"]}
        with closing(pdfium.PdfDocument(source)) as pdf:
            item["form_type"] = pdf.get_formtype()
        if not case.get("xfa"):
            with control(source, True) as expected, control(source, False) as missing:
                expected.save(output / f"{case['id']}.expected.png")
                with ImageChops.difference(expected, missing) as delta:
                    item["form_effect_bbox"] = delta.getbbox()
                rendered = render_page_png(source, 1)
                (output / f"{case['id']}.review.png").write_bytes(rendered)
                with (
                    Image.open(io.BytesIO(rendered)) as image,
                    ImageChops.difference(image.convert("RGB"), expected) as delta,
                ):
                    item["review_matches_form_renderer"] = delta.getbbox() is None
        else:
            try:
                render_page_png(source, 1)
                item["render_status"] = "accepted"
            except ValueError as error:
                item["render_status"] = "rejected"
                item["render_error"] = str(error)
        try:
            document = load_pdf(source)
            assert document_from_dict(json.loads(json.dumps(asdict(document)))) == document
            item["load_status"] = "loaded"
            item["document"] = asdict(document)
            item["visible_native_claim"] = asdict(
                verify(
                    Amount(total=Evidenced(value=42, evidence=["Visible native amount: $42.00"])),
                    document,
                ).fields[0]
            )
            if case.get("cover"):
                item["covered_claim"] = asdict(
                    verify(
                        Amount(total=Evidenced(value=900, evidence=["Authorized total: $900.00"])),
                        document,
                    ).fields[0]
                )
            if case.get("value"):
                # A displayed form value is not a native page-text occurrence.
                item["widget_value_in_native_text"] = case["value"] in document.full_text()
        except EmptyDocumentError:
            item["load_status"] = "empty_native_text"
        except ValueError as error:
            item["load_status"] = "rejected"
            item["load_error"] = str(error)
        assert path.read_bytes() == source
        results.append(item)
    result = {"pypdfium2": str(PYPDFIUM_INFO), "pdfium": str(PDFIUM_INFO), "cases": results}
    (output / "replay.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = replay(args.output)
    print(
        json.dumps(
            {
                "cases": len(result["cases"]),
                "review_mismatches": [
                    c["id"]
                    for c in result["cases"]
                    if c.get("review_matches_form_renderer") is False
                ],
                "xfa": result["cases"][-1]["load_status"],
            }
        )
    )


if __name__ == "__main__":
    main()
