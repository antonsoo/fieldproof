"""Independent final-pixel checks: each renderer against an omitted-ink reference."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import pypdfium2 as pdfium
from generate import HERE, draw_case
from PIL import Image


def pixels(path: Path, engine: str, directory: Path) -> tuple[tuple[int, int], bytes]:
    if engine == "pdfium":
        with pdfium.PdfDocument(path) as document:
            page = document[0]
            bitmap = page.render(scale=2.0)
            image = bitmap.to_pil()
            try:
                rgb = image.convert("RGB")
                try:
                    return rgb.size, rgb.tobytes()
                finally:
                    rgb.close()
            finally:
                image.close()
                bitmap.close()
                page.close()
    prefix = directory / "poppler"
    subprocess.run(
        ["pdftoppm", "-r", "144", "-singlefile", "-png", str(path), str(prefix)],
        capture_output=True,
        check=True,
    )
    with Image.open(prefix.with_suffix(".png")) as image:
        rgb = image.convert("RGB")
        try:
            return rgb.size, rgb.tobytes()
        finally:
            rgb.close()


def main() -> None:
    rows = []
    with tempfile.TemporaryDirectory(prefix="fieldproof-flat-raster-") as temporary:
        directory = Path(temporary)
        for case in json.loads((HERE / "cases.json").read_text()):
            # Omit only the hidden leading digit for mixed cases. All following
            # character positions remain fixed; no text reflow can explain equality.
            control = directory / "omitted.pdf"
            control.write_bytes(draw_case(case, omit_hidden=True))
            if not case["hidden"]:
                # Visible cases need a counterfactual too: omit their full text.
                omitted = {**case, "hidden": True}
                control.write_bytes(draw_case(omitted, omit_hidden=True))
            for engine in ("pdfium", "poppler"):
                actual = pixels(HERE / "fixtures" / f"{case['id']}.pdf", engine, directory)
                expected = pixels(control, engine, directory)
                equal = actual == expected
                rows.append(
                    {
                        "case": case["id"],
                        "engine": engine,
                        "expectedHidden": case["hidden"],
                        "equalToOmittedInk": equal,
                        "size": actual[0],
                        "rgbSha256": hashlib.sha256(actual[1]).hexdigest(),
                        "controlRgbSha256": hashlib.sha256(expected[1]).hexdigest(),
                    }
                )
    report = {
        "scope": __doc__,
        "dpi": 144,
        "checks": len(rows),
        "mismatches": sum(r["expectedHidden"] != r["equalToOmittedInk"] for r in rows),
        "rows": rows,
    }
    (HERE / "results/pixels.json").write_text(json.dumps(report, indent=2) + "\n")
    print({k: v for k, v in report.items() if k != "rows"})
    assert report["mismatches"] == 0, [
        r for r in rows if r["expectedHidden"] != r["equalToOmittedInk"]
    ]


if __name__ == "__main__":
    main()
