"""Download the annotated receipts the study reads: CORD v2 and a SROIE 2019 mirror.

    python3 studies/cord-grounding/fetch.py

Neither dataset is committed. This fetches the parquet files at pinned Hugging Face
revisions into studies/cord-grounding/cache/ and checks each against the SHA-256 recorded in
manifest.json (fetched 2026-10-08). About 1.2 GB. The images in the files are never read.

    CORD v2   https://huggingface.co/datasets/naver-clova-ix/cord-v2   (CC BY 4.0)
    SROIE     https://huggingface.co/datasets/arvindrajan92/sroie_document_understanding
              (card says MIT; it is a third party's re-upload of the ICDAR 2019 SROIE
              receipts with their own extra line labels. The terms of the original
              competition data were not found tonight; nothing from it is redistributed here.)
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
MANIFEST = json.loads((HERE / "manifest.json").read_text())


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    cache = HERE / "cache"
    cache.mkdir(exist_ok=True)
    for entry in MANIFEST["files"]:
        target = cache / entry["name"]
        if not target.exists():
            request = urllib.request.Request(
                entry["url"], headers={"User-Agent": "fieldproof-study (local research)"}
            )
            with urllib.request.urlopen(request, timeout=600) as response, target.open("wb") as out:
                while chunk := response.read(1 << 20):
                    out.write(chunk)
        digest = sha256(target)
        status = "ok" if digest == entry["sha256"] else f"MISMATCH (got {digest})"
        print(f"{target.name}: {target.stat().st_size:,} bytes, sha256 {status}")


if __name__ == "__main__":
    main()
