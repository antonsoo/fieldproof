"""Replay each convention control through the actual API and bounded workers."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from importlib.metadata import version
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    import pypdfium2 as pdfium
    from fastapi.testclient import TestClient

    import fieldproof
    from fieldproof.ground import values
    from fieldproof.server.app import app
    from fieldproof.server.store import store

    package = Path(fieldproof.__file__).resolve().parent
    assert package.is_relative_to(Path(sys.prefix).resolve())
    pdf = (HERE / "fixtures/conventions.pdf").read_bytes()
    cases = json.loads((HERE / "conventions.json").read_text())
    fixture = json.loads((HERE / "fixtures/review.json").read_text())
    observations = []
    store._sessions.clear()
    try:
        with pdfium.PdfDocument(pdf) as source, TestClient(app) as client:
            for i, case in enumerate(cases):
                buffer = BytesIO()
                with pdfium.PdfDocument.new() as page:
                    page.import_pages(source, [i])
                    page.save(buffer)
                upload = client.post(
                    "/api/documents",
                    files={"file": ("isolated-control.pdf", buffer.getvalue(), "application/pdf")},
                )
                assert upload.status_code == 200, upload.text
                url = f"/api/documents/{upload.json()['id']}"
                for value, expected in zip([60, 60000], case["total_statuses"], strict=True):
                    fixture["data"]["total"] = {"value": value, "evidence": ["Total 60.000"]}
                    response = client.post(
                        url + "/extract",
                        data={"schema": "invoice", "provider": "fixture"},
                        files={
                            "fixture": (
                                "claims.json",
                                json.dumps(fixture).encode(),
                                "application/json",
                            )
                        },
                    )
                    assert response.status_code == 200, response.text
                    report = response.json()["report"]
                    field = next(f for f in report["fields"] if f["path"] == "total")
                    assert field["status"] == expected, (case["id"], value, field)
                    assert client.get(url + "/report").json()["report"] == report
                    exported = next(
                        f for f in client.get(url + "/export.json").json() if f["field"] == "total"
                    )
                    assert exported["verification_status"] == expected
                    observations.append(
                        {"id": case["id"], "value": value, "expected": expected, "field": field}
                    )
    finally:
        store._sessions.clear()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "scope": (
                    "Actual upload/extract workers and export; isolated controls, no model calls."
                ),
                "python": platform.python_version(),
                "packages": {
                    name: version(name)
                    for name in ["fieldproof", "pdfplumber", "pypdfium2", "pydantic"]
                },
                "installed_under_prefix": True,
                "parser_sha256": hashlib.sha256(Path(values.__file__).read_bytes()).hexdigest(),
                "source_sha256": {
                    str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(package.rglob("*.py"))
                },
                "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                "observations": observations,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(f"{len(observations)} isolated worker/API convention claims and exports match.")


if __name__ == "__main__":
    main()
