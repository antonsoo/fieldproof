"""Exercise a real server restart; runs against a chosen source checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import httpx


@contextmanager
def server(source, python, log, *, installed=False):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "PYTHONPATH": str(source / "src")}
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("FIELDPROOF_STATIC_DIR", None)
    if installed:
        env.pop("PYTHONPATH", None)
    with log.open("ab") as output:
        process = subprocess.Popen(
            [python, "-m", "uvicorn", "fieldproof.server.app:app", "--port", str(port)],
            cwd=source,
            env=env,
            stdout=output,
            stderr=output,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=60) as client:
                for _ in range(200):
                    try:
                        if client.get("/api/schemas").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    if process.poll() is not None:
                        raise RuntimeError(f"Server exited; see {log}")
                    time.sleep(0.05)
                else:
                    raise RuntimeError("Server did not start")
                yield client
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def ok(response):
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    records = []
    saved = []
    with server(source, args.python, out.with_suffix(".log"), installed=args.installed) as client:
        for sample, schema in [
            ("invoice", "invoice"),
            ("receipt", "receipt"),
            ("contract", "contract"),
            ("line-arithmetic", "invoice"),
        ]:
            pdf = (source / f"examples/{sample}.pdf").read_bytes()
            fixture = (source / f"examples/fixtures/{sample}.json").read_bytes()
            doc = ok(client.post("/api/documents", files={"file": (sample + ".pdf", pdf)}))
            root = f"/api/documents/{doc['id']}"
            extraction = ok(
                client.post(
                    root + "/extract",
                    data={"schema": schema, "provider": "fixture"},
                    files={"fixture": ("fixture.json", fixture)},
                )
            )
            # All four decision states, retaining a correction after rejection.
            fields = extraction["report"]["fields"]
            for index, field in enumerate(fields[:3]):
                value = field["value"]
                correction = (
                    not value
                    if isinstance(value, bool)
                    else (
                        value + 0.25
                        if isinstance(value, (float, int))
                        else "00042 = literal correction"
                    )
                )
                action = "approve" if index == 0 else "edit"
                ok(
                    client.post(
                        root + "/review",
                        json={"path": field["path"], "action": action, "value": correction},
                    )
                )
                if index == 2:
                    ok(
                        client.post(
                            root + "/review", json={"path": field["path"], "action": "reject"}
                        )
                    )
            original = ok(client.get(root + "/report"))
            exports = {
                ext: client.get(root + "/export." + ext).content for ext in ["json", "csv", "xlsx"]
            }
            started = time.perf_counter()
            archive = client.get(root + "/archive")
            save_ms = (time.perf_counter() - started) * 1000
            record = {
                "sample": sample,
                "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                "fields": len(fields),
                "save_archive_status": archive.status_code,
                "save_ms": round(save_ms, 3),
            }
            records.append(record)
            saved.append((doc, original, exports, archive.content, record))
    # All memory has gone. The next process has no API key or previous session state.
    with server(source, args.python, out.with_suffix(".log"), installed=args.installed) as client:
        assert ok(client.get("/api/documents"))["documents"] == []
        for doc, original, exports, archive, record in saved:
            record["old_session_after_restart"] = client.get(
                f"/api/documents/{doc['id']}/report"
            ).status_code
            started = time.perf_counter()
            restored = client.post(
                "/api/archives", files={"file": ("review.zip", archive, "application/zip")}
            )
            record["restore_status"] = restored.status_code
            record["restore_ms"] = round((time.perf_counter() - started) * 1000, 3)
            if record["save_archive_status"] == 200:
                restored_doc = ok(restored)["document"]
                assert restored_doc["id"] != doc["id"]
                root = f"/api/documents/{restored_doc['id']}"
                result = ok(client.get(root + "/report"))
                assert result == original
                record["report_and_decisions_equal"] = True
                record["exports_equal"] = {}
                for ext, expected in exports.items():
                    actual = client.get(root + "/export." + ext)
                    actual.raise_for_status()
                    assert actual.content == expected
                    record["exports_equal"][ext] = True
                page = client.get(root + "/pages/1.png")
                page.raise_for_status()
                record["rendered_page_bytes"] = len(page.content)
                record["archive_bytes"] = len(archive)
                record["archive_sha256"] = hashlib.sha256(archive).hexdigest()
                (out.parent / f"{record['sample']}.fieldproof.zip").write_bytes(archive)
    out.write_text(
        json.dumps(
            {
                "cases": records,
                "model_calls": 0,
                "inputs": "Four repository synthetic PDF/fixture pairs",
            },
            indent=2,
        )
        + "\n"
    )
    print(out.read_text())


if __name__ == "__main__":
    main()
