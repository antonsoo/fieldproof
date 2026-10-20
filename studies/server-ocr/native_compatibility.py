"""Run in separate before/after interpreters to compare native API bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

import fieldproof
from fieldproof.server.app import app

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with TestClient(app) as client:
        response = client.post(
            "/api/documents",
            files={"file": ("invoice.pdf", (ROOT / "examples/invoice.pdf").read_bytes())},
        )
        response.raise_for_status()
        doc = response.json()
        root = "/api/documents/" + doc["id"]
        extraction = client.post(
            root + "/extract",
            data={"schema": "invoice", "provider": "fixture"},
            files={
                "fixture": ("invoice.json", (ROOT / "examples/fixtures/invoice.json").read_bytes())
            },
        )
        extraction.raise_for_status()
        client.post(
            root + "/review", json={"path": "total", "action": "edit", "value": 123.45}
        ).raise_for_status()
        report = client.get(root + "/report").content
        (args.out / "extraction.json").write_bytes(report)
        hashes = {"extraction.json": hashlib.sha256(report).hexdigest()}
        for scope in ["all", "reviewed"]:
            for extension in ["json", "csv", "xlsx"]:
                exported = client.get(root + f"/export.{extension}?scope={scope}")
                exported.raise_for_status()
                name = f"{scope}.{extension}"
                (args.out / name).write_bytes(exported.content)
                hashes[name] = hashlib.sha256(exported.content).hexdigest()
        archive = client.get(root + "/archive")
        archive.raise_for_status()
        (args.out / "review.zip").write_bytes(archive.content)
        hashes["review.zip"] = hashlib.sha256(archive.content).hexdigest()
    (args.out / "hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")
    # The absolute path stays in throwaway output, not the retained receipt.
    print(fieldproof.__file__)
    print(json.dumps(hashes, indent=2))


if __name__ == "__main__":
    main()
