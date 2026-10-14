"""Capture a real installed CLI's default and opt-in mixed-document results."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, type=Path)
    args = parser.parse_args()
    interpreter = str(args.python.absolute())
    inputs = Path(__file__).resolve().parent / "inputs"
    with tempfile.TemporaryDirectory(prefix="mixed-demo-") as temporary:
        for file in ["mixed.pdf", "mixed.json"]:
            shutil.copy(inputs / file, Path(temporary) / file)
        for mode, extra in [
            ("Default native loader", []),
            ("Explicit page OCR", ["--ocr-missing-pages"]),
        ]:
            print(mode)
            command = [
                interpreter,
                "-m",
                "fieldproof.cli",
                "extract",
                "mixed.pdf",
                "--fixture",
                "mixed.json",
                "--out",
                "result.json",
                *extra,
            ]
            result = subprocess.run(
                command, cwd=temporary, capture_output=True, text=True, check=False
            )
            assert result.returncode == 0, result.stderr
            print(result.stdout, end="")
            print(result.stderr, end="")
            report = json.loads((Path(temporary) / "result.json").read_text())["report"]
            if extra:
                assert report["counts"]["verified"] == 6
                print(f"OCR pages: {report['ocr']['processed_pages']}")
            else:
                assert report["counts"]["verified"] == 3
            print()


if __name__ == "__main__":
    main()
