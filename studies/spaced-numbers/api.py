"""Run the actual upload/extraction workers and exports in one installed environment."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    from fastapi.testclient import TestClient

    from fieldproof.document.model import document_from_dict
    from fieldproof.ground import values
    from fieldproof.server.app import app
    from fieldproof.server.store import store
    from fieldproof.verify import verify

    pdf = (HERE / "fixtures/review.pdf").read_bytes()
    fixture = (HERE / "fixtures/review.json").read_bytes()
    store._sessions.clear()
    started = perf_counter()
    try:
        with TestClient(app) as client:
            upload = client.post(
                "/api/documents", files={"file": ("grouping.pdf", pdf, "application/pdf")}
            )
            assert upload.status_code == 200, upload.text
            url = f"/api/documents/{upload.json()['id']}"
            observations = []
            for value in (234.56, 1234.56):
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
                report = response.json()["report"]
                field = next(f for f in report["fields"] if f["path"] == "total")
                assert client.get(url + "/report").json()["report"] == report
                exported = next(
                    f for f in client.get(url + "/export.json").json() if f["field"] == "total"
                )
                assert exported["verification_status"] == field["status"]
                assert report["counts"]["verified"] == (4 if field["status"] == "verified" else 3)
                observations.append({"value": value, "field": field, "exported": exported})
            image = client.get(url + "/pages/1.png")
            assert image.status_code == 200 and image.content.startswith(b"\x89PNG\r\n\x1a\n")
            # The worker wire format must retain the boxes that settle cell gaps.
            session = next(iter(store._sessions.values()))
            document = session.document
            assert document is not None
            rebuilt = document_from_dict(asdict(document))
            assert rebuilt == document
            assert session.extraction is not None
            assert (
                verify(session.extraction.data, rebuilt).to_dict()
                == verify(session.extraction.data, document).to_dict()
            )
            actual = [row["field"]["status"] for row in observations]
            output = {
                "scope": "Installed API and bounded workers; fixture provider, no model calls.",
                "parser_sha256": hashlib.sha256(Path(values.__file__).read_bytes()).hexdigest(),
                "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                "fixture_sha256": hashlib.sha256(fixture).hexdigest(),
                "seconds": perf_counter() - started,
                "wire_roundtrip_equal": True,
                "actual": actual,
                "expected": ["needs_review", "needs_review"],
                "observations": observations,
                "image_sha256": hashlib.sha256(image.content).hexdigest(),
            }
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
            print(f"API fragment / whole grouped amount: {actual}; expected {output['expected']}")
            if not args.observe_only:
                assert actual == output["expected"]
    finally:
        store._sessions.clear()


if __name__ == "__main__":
    main()
