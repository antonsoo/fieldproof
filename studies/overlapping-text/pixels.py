"""Compare each renderer's final pixels with an independently authored omission.

The baseline PDF does not paint the old nine in the control. Equality proves
the old nine cannot explain the observed ink, even though its box contains it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import pypdfium2 as pdfium
from generate import CASES, HERE, draw_case
from PIL import Image


def render(path: Path, engine: str, directory: Path) -> tuple[tuple[int, int], bytes]:
    if engine == "pdfium":
        with pdfium.PdfDocument(path) as document:
            page = document[0]
            bitmap = page.render(scale=2)
            image = bitmap.to_pil()
            try:
                with image.convert("RGB") as rgb:
                    return rgb.size, rgb.tobytes()
            finally:
                image.close()
                bitmap.close()
                page.close()
    prefix = directory / "render"
    subprocess.run(
        ["pdftoppm", "-cropbox", "-r", "144", "-singlefile", "-png", str(path), str(prefix)],
        capture_output=True, check=True,
    )
    with Image.open(prefix.with_suffix(".png")) as image, image.convert("RGB") as rgb:
        return rgb.size, rgb.tobytes()


def main() -> None:
    rows = []
    with tempfile.TemporaryDirectory(prefix="fieldproof-overlap-") as temporary:
        directory = Path(temporary)
        for case in CASES:
            control = directory / "omitted.pdf"
            control.write_bytes(draw_case(case, omit_nine=True))
            for engine in ("pdfium", "poppler"):
                actual = render(HERE / "fixtures" / f"{case['id']}.pdf", engine, directory)
                omitted = render(control, engine, directory)
                rows.append({
                    "case": case["id"], "engine": engine,
                    "expectedEqual": case["review"], "equal": actual == omitted,
                    "size": actual[0],
                    "rgbSha256": hashlib.sha256(actual[1]).hexdigest(),
                    "omittedRgbSha256": hashlib.sha256(omitted[1]).hexdigest(),
                })
    report = {"dpi": 144, "checks": len(rows),
              "mismatches": sum(row["expectedEqual"] != row["equal"] for row in rows),
              "rows": rows}
    (HERE / "results/pixels.json").write_text(json.dumps(report, indent=2) + "\n")
    print({k: v for k, v in report.items() if k != "rows"})
    assert report["mismatches"] == 0


if __name__ == "__main__":
    main()
