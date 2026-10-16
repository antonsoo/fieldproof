"""Compare each PDF to its omitted-text reference in PDFium and Poppler."""

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import pypdfium2 as pdfium
from generate import ROOT, draw_case
from PIL import Image


def pixels(path, engine, work):
    if engine == "pdfium":
        with pdfium.PdfDocument(path) as document:
            page = document[0]
            bitmap = page.render(scale=1)
            image = bitmap.to_pil().convert("RGB")
            result = image.size, image.tobytes()
            bitmap.close()
            page.close()
            return result
    prefix = work / "render"
    subprocess.run(["pdftoppm", "-r", "72", "-singlefile", "-png", str(path), str(prefix)],
                   check=True, capture_output=True)
    with Image.open(prefix.with_suffix(".png")) as image:
        rgb = image.convert("RGB")
        return rgb.size, rgb.tobytes()


def main():
    observations = []
    with tempfile.TemporaryDirectory(prefix="fieldproof-clipping-") as directory:
        work = Path(directory)
        for case in json.loads((ROOT / "cases.json").read_text()):
            reference = work / "reference.pdf"
            reference.write_bytes(draw_case(case, omit_alternate=True))
            for engine in ("pdfium", "poppler"):
                actual = pixels(ROOT / "fixtures" / f"{case['id']}.pdf", engine, work)
                expected = pixels(reference, engine, work)
                equal = actual == expected
                observations.append({"case": case["id"], "engine": engine,
                                     "expected_hidden": case["hidden"],
                                     "equal_to_omitted_text": equal,
                                     "sha256_rgb": hashlib.sha256(actual[1]).hexdigest()})
                if case["id"] == "partial":
                    full_reference = work / "unclipped.pdf"
                    full_reference.write_bytes(draw_case({"id": "unclipped", "hidden": False}))
                    full = pixels(full_reference, engine, work)
                    observations[-1]["differs_from_unclipped_text"] = actual != full
                    assert actual != full, "The partial control must actually clip the text"
    result = {"checks": len(observations),
              "mismatches": sum(o["expected_hidden"] != o["equal_to_omitted_text"] for o in observations),
              "observations": observations}
    destination = ROOT / "results/pixels.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print({k: v for k, v in result.items() if k != "observations"})
    for entry in observations:
        if entry["expected_hidden"] != entry["equal_to_omitted_text"]:
            print(entry)
    assert result["mismatches"] == 0


if __name__ == "__main__":
    main()
