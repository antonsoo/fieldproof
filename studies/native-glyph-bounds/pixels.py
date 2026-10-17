"""Check each engine against an authored PDF which never draws the old nine."""

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
        capture_output=True,
        check=True,
    )
    with Image.open(prefix.with_suffix(".png")) as image, image.convert("RGB") as rgb:
        return rgb.size, rgb.tobytes()


def main() -> None:
    rows = []
    with tempfile.TemporaryDirectory(prefix="fieldproof-native-bounds-") as temporary:
        directory = Path(temporary)
        for case in CASES:
            source = HERE / "fixtures" / f"{case['id']}.pdf"
            assert source.read_bytes() == draw_case(case), case["id"]
            control = directory / "omitted.pdf"
            control.write_bytes(draw_case(case, omit_nine=True))
            for engine in ("pdfium", "poppler"):
                actual, omitted = (
                    render(source, engine, directory),
                    render(control, engine, directory),
                )
                rows.append(
                    {
                        "case": case["id"],
                        "engine": engine,
                        "expected_equal": case.get("hidden", False),
                        "equal": actual == omitted,
                        "size": actual[0],
                        "rgb_sha256": hashlib.sha256(actual[1]).hexdigest(),
                        "omitted_rgb_sha256": hashlib.sha256(omitted[1]).hexdigest(),
                    }
                )
    report = {
        "dpi": 144,
        "checks": len(rows),
        "mismatches": sum(row["expected_equal"] != row["equal"] for row in rows),
        "rows": rows,
    }
    (HERE / "results/pixels.json").write_text(json.dumps(report, indent=2) + "\n")
    print({k: v for k, v in report.items() if k != "rows"})
    assert report["mismatches"] == 0


if __name__ == "__main__":
    main()
