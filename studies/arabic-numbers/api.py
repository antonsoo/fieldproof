"""Observe the actual worker upload, fixture extraction and export on another source/wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    from fastapi.testclient import TestClient

    from fieldproof.ground import values
    from fieldproof.server.app import app
    from fieldproof.server.store import store

    pdf = (HERE / "fixtures/review.pdf").read_bytes()
    fixture = (HERE / "fixtures/review.json").read_bytes()
    started = perf_counter()
    store._sessions.clear()
    try:
        with TestClient(app) as client:
            upload = client.post(
                "/api/documents", files={"file": ("locale.pdf", pdf, "application/pdf")}
            )
            assert upload.status_code == 200, upload.text
            url = f"/api/documents/{upload.json()['id']}"
            verdicts = []
            for value in (234, 1234.56):
                payload = json.loads(fixture)
                payload["data"]["total"]["value"] = value
                response = client.post(
                    url + "/extract",
                    data={"schema": "invoice", "provider": "fixture"},
                    files={
                        "fixture": ("claims.json", json.dumps(payload).encode(), "application/json")
                    },
                )
                assert response.status_code == 200, response.text
                result = response.json()["report"]
                field = next(f for f in result["fields"] if f["path"] == "total")
                assert client.get(url + "/report").json()["report"] == result
                exported = next(
                    f for f in client.get(url + "/export.json").json() if f["field"] == "total"
                )
                assert exported["verification_status"] == field["status"]
                verdicts.append({"value": value, "field": field, "exported": exported})
            image = client.get(url + "/pages/1.png")
            assert image.status_code == 200 and image.content.startswith(b"\x89PNG\r\n\x1a\n")
            expected = ["needs_review", "verified"]
            actual = [v["field"]["status"] for v in verdicts]
            output = {
                "scope": "Actual API and bounded PDF workers, fixture provider; no model calls.",
                "number_parser_sha256": hashlib.sha256(
                    Path(values.__file__).read_bytes()
                ).hexdigest(),
                "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                "fixture_sha256": hashlib.sha256(fixture).hexdigest(),
                "seconds": perf_counter() - started,
                "expected": expected,
                "actual": actual,
                "agrees": actual == expected,
                "verdicts": verdicts,
                "image_sha256": hashlib.sha256(image.content).hexdigest(),
            }
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
            print(f"API wrong/correct claim: {actual}; expected {expected}")
            if not args.observe_only:
                assert output["agrees"]
    finally:
        store._sessions.clear()


if __name__ == "__main__":
    main()
