"""Measure the current Python installation and retain complete verification outputs.

PDF parsing is outside the library timer. The API measurement includes the actual
disposable verification worker, with its unchanged application/resource limits.
Use --skip-api when the installed runtime has no httpx development dependency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import time
from pathlib import Path

import fieldproof
from fieldproof.document.loader import load_pdf
from fieldproof.schemas.invoice import Invoice
from fieldproof.verify.engine import verify

HERE = Path(__file__).resolve().parent


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, nargs="+", default=[25, 50, 100])
    parser.add_argument("--api-rows", type=int, nargs="+", default=[100, 400])
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--skip-api", action="store_true")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    args.work.mkdir(parents=True, exist_ok=True)
    fixtures = HERE / "fixtures"
    results = []
    for rows in args.rows:
        pdf = fixtures / f"rows-{rows}.pdf"
        fixture = fixtures / f"rows-{rows}.json"
        document = load_pdf(pdf)
        data = Invoice.model_validate_json(fixture.read_bytes())
        times = []
        report_bytes = b""
        for _ in range(args.repeat):
            start = time.perf_counter()
            report = verify(data, document)
            times.append(time.perf_counter() - start)
            current = (json.dumps(report.to_dict(), indent=2) + "\n").encode()
            assert not report_bytes or current == report_bytes
            report_bytes = current
        (args.work / f"report-{rows}.json").write_bytes(report_bytes)
        result = {
            "rows": rows,
            "pages": document.page_count,
            "words": sum(len(page.words) for page in document.pages),
            "fields": len(report.fields),
            "counts": report.counts,
            "seconds": times,
            "median_seconds": statistics.median(times),
            "pdf_sha256": digest(pdf.read_bytes()),
            "fixture_sha256": digest(fixture.read_bytes()),
            "complete_report_sha256": digest(report_bytes),
        }
        results.append(result)
        print(json.dumps(result), flush=True)

    api = []
    if not args.skip_api:
        from fastapi.testclient import TestClient

        from fieldproof.server.app import app

        with TestClient(app) as client:
            for rows in args.api_rows:
                pdf = fixtures / f"rows-{rows}.pdf"
                fixture = fixtures / f"rows-{rows}.json"
                uploaded = client.post(
                    "/api/documents",
                    files={
                        "file": (pdf.name, pdf.read_bytes(), "application/pdf"),
                    },
                )
                assert uploaded.status_code == 200, uploaded.text
                document_id = uploaded.json()["id"]
                start = time.perf_counter()
                response = client.post(
                    f"/api/documents/{document_id}/extract",
                    data={
                        "schema": "invoice",
                        "provider": "fixture",
                    },
                    files={"fixture": (fixture.name, fixture.read_bytes(), "application/json")},
                )
                elapsed = time.perf_counter() - start
                body = response.json()
                result = {
                    "rows": rows,
                    "upload_status": uploaded.status_code,
                    "extraction_status": response.status_code,
                    "seconds": elapsed,
                }
                if response.status_code == 200:
                    report_bytes = (json.dumps(body["report"], indent=2) + "\n").encode()
                    (args.work / f"api-report-{rows}.json").write_bytes(report_bytes)
                    result.update(
                        counts=body["report"]["counts"], complete_report_sha256=digest(report_bytes)
                    )
                else:
                    result["error"] = body
                api.append(result)
                print(json.dumps(result), flush=True)
                assert client.delete(f"/api/documents/{document_id}").status_code == 204

    module_root = Path(fieldproof.__file__).parent
    modules = ("ground/align.py", "verify/engine.py", "document/worker.py", "server/pdf_work.py")
    result = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "implementation_sha256": {
            module: digest((module_root / module).read_bytes()) for module in modules
        },
        "library": results,
        "api": api,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
