"""Restore captured archives through a real, empty installed server.

Run before and after restarting the process. No model call or source-tree import.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--reference", type=Path, help="Replay from the restoring runtime")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    expected = json.loads((args.capture / "capture.json").read_text())
    result = []
    with httpx.Client(base_url=args.url, timeout=65) as client:
        listing = client.get("/api/documents")
        listing.raise_for_status()
        assert listing.json()["documents"] == [], "Use a fresh, empty server"
        for case in expected["cases"]:
            if not case.get("restoreExact"):
                continue
            key = f"{case['name']}-{case['mode']}"
            archive = (args.capture / key / "review.zip").read_bytes()
            response = client.post("/api/archives", files={"file": ("review.zip", archive)})
            response.raise_for_status()
            data = response.json()
            original = json.loads((args.capture / key / "original-report.json").read_text())
            reference = json.loads(
                ((args.reference or args.capture) / key / "original-report.json").read_text()
            )
            assert data["extraction"]["report"] == reference["report"], key
            assert data["extraction"]["data"] == original["data"], key
            assert data["document"].get("text_mode", "native") == case["mode"], key
            root = "/api/documents/" + data["document"]["id"]
            rows = client.get(root + "/export.json?scope=reviewed")
            rows.raise_for_status()
            assert rows.json() == case["reviewedRows"], key
            image = client.get(root + "/pages/1.png")
            image.raise_for_status()
            assert image.content.startswith(b"\x89PNG\r\n\x1a\n")
            result.append(
                {
                    "case": key,
                    "runtimeReferenceReportExact": True,
                    "sourceReportExact": data["extraction"]["report"] == original["report"],
                    "claimsExact": True,
                    "reviewedExportExact": True,
                    "pageRendered": True,
                }
            )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"url": args.url, "results": result}, indent=2) + "\n")
    print(f"{len(result)} archives restored in the installed server")


if __name__ == "__main__":
    main()
