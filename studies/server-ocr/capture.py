"""Actual API/recognizer/export/archive replay. No model or remote service is called.

Run with the OCR extra, Tesseract and English data installed. --demo writes
only the new attributed CORD example; existing demo data is left untouched.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient

from fieldproof.document.render import render_page_png
from fieldproof.server.app import app
from fieldproof.server.store import store

ROOT = Path(__file__).resolve().parents[2]
STUDY = Path(__file__).resolve().parent


def sha(content):
    return hashlib.sha256(content).hexdigest()


def recognition_reference(session, target):
    """Direct native TSV bypasses pytesseract, document conversion and API transport."""
    ocr = session.document.ocr
    if not ocr:
        return []
    results = []
    for page in session.document.pages:
        if ocr.processed_pages is not None and page.number not in ocr.processed_pages:
            continue
        png = render_page_png(session.pdf_bytes, page.number)
        image = target / f"ocr-page-{page.number}.png"
        image.write_bytes(png)
        result = subprocess.run(
            ["tesseract", str(image), "stdout", "-l", "eng", "-c", "tessedit_create_tsv=1"],
            check=True,
            timeout=10,
            capture_output=True,
            env={**os.environ, "OMP_THREAD_LIMIT": "1", "OMP_NUM_THREADS": "1"},
        )
        (target / f"page-{page.number}.tsv").write_bytes(result.stdout)
        rows = list(
            csv.DictReader(
                result.stdout.decode().splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE
            )
        )
        expected = []
        for row in rows:
            text = row["text"].strip()
            if not text:
                continue
            x, y, w, h = (int(row[k]) for k in ["left", "top", "width", "height"])
            expected.append(
                {
                    "text": text,
                    "bbox": {"x0": x / 2, "top": y / 2, "x1": (x + w) / 2, "bottom": (y + h) / 2},
                }
            )
        actual = [{"text": word.text, "bbox": asdict(word.bbox)} for word in page.words]
        assert actual == expected, (session.filename, page.number, actual, expected)
        results.append(
            {
                "page": page.number,
                "words": len(expected),
                "pngSha256": sha(png),
                "tsvSha256": sha(result.stdout),
            }
        )
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    cases = [
        (
            "cord",
            ROOT / "examples/recorded/cord/cord-test-0000.pdf",
            ROOT / "examples/recorded/cord/fixture.json",
            "receipt",
        ),
        (
            "saved-form",
            ROOT / "studies/form-appearances/fixtures/covered-native-total.pdf",
            STUDY / "fixtures/form-hidden-claim.json",
            "invoice",
        ),
        (
            "mixed",
            STUDY / "fixtures/mixed-source.pdf",
            STUDY / "fixtures/mixed-fixture.json",
            "invoice",
        ),
    ]
    result = {
        "python": sys.version.split()[0],
        "tesseract": subprocess.check_output(["tesseract", "--version"]).decode().splitlines()[0],
        "cases": [],
    }
    executable = shutil.which("tesseract")
    result["tesseractBinarySha256"] = sha(Path(executable).read_bytes())
    original_inputs = {
        str(p.relative_to(ROOT)): sha(p.read_bytes())
        for _, pdf, fixture, _ in cases
        for p in [pdf, fixture]
    }
    with TestClient(app) as client:
        for name, pdf, fixture, schema in cases:
            for mode in ["native", "ocr-missing", "ocr-all"]:
                store._sessions.clear()
                target = args.out / f"{name}-{mode}"
                target.mkdir(parents=True, exist_ok=True)
                response = client.post(
                    "/api/documents",
                    data={"text_mode": mode},
                    files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")},
                )
                case = {
                    "name": name,
                    "mode": mode,
                    "pdfSha256": sha(pdf.read_bytes()),
                    "fixtureSha256": sha(fixture.read_bytes()),
                    "uploadStatus": response.status_code,
                }
                if response.status_code != 200:
                    assert name == "cord" and mode == "native" and response.status_code == 422, (
                        response.json()
                    )
                    case["error"] = response.json()
                    result["cases"].append(case)
                    continue
                document = response.json()
                root = f"/api/documents/{document['id']}"
                extracted = client.post(
                    root + "/extract",
                    data={"schema": schema, "provider": "fixture"},
                    files={"fixture": (fixture.name, fixture.read_bytes(), "application/json")},
                )
                extracted.raise_for_status()
                original = extracted.json()
                (target / "original-report.json").write_text(json.dumps(original, indent=2) + "\n")
                session = store.get(document["id"])
                assert session is not None
                reference = recognition_reference(session, target)
                case["nativeReference"] = reference
                case["fields"] = [
                    {k: field[k] for k in ["path", "value", "status", "matched_text", "page"]}
                    for field in original["report"]["fields"]
                ]
                case["ocr"] = original["report"].get("ocr")
                case["document"] = document
                page = client.get(root + "/pages/1.png")
                page.raise_for_status()
                (target / "page-1.png").write_bytes(page.content)
                if args.demo and name == "cord" and mode == "ocr-all":
                    directory = ROOT / "web/public/demo-data/cord-ocr"
                    directory.mkdir(parents=True, exist_ok=True)
                    static_document = {
                        key: document[key]
                        for key in ["filename", "page_count", "pages", "text_mode", "ocr"]
                    }
                    static_document["id"] = "cord-ocr"
                    static_document["source_credit"] = (
                        "CORD v2 test #0, NAVER CLOVA, CC BY 4.0. "
                        "Photo unchanged; fixture claims authored; header redacted."
                    )
                    (directory / "data.json").write_text(
                        json.dumps({"document": static_document, "extraction": original}, indent=2)
                        + "\n"
                    )
                    (directory / "page-1.png").write_bytes(page.content)
                    shutil.copy(
                        ROOT / "examples/recorded/cord/source.json", directory / "source.json"
                    )
                    shutil.copy(ROOT / "examples/recorded/cord/NOTICE.md", directory / "NOTICE.md")
                    index_file = ROOT / "web/public/demo-data/index.json"
                    index = json.loads(index_file.read_text())
                    if not any(item["id"] == "cord-ocr" for item in index):
                        index.append({"id": "cord-ocr", "label": "Scanned CORD receipt"})
                        index_file.write_text(json.dumps(index, indent=2) + "\n")
                if name == "saved-form":
                    edited = client.post(
                        root + "/review", json={"path": "total", "action": "edit", "value": 100}
                    )
                    edited.raise_for_status()
                else:
                    approved = client.post(
                        root + "/review", json={"path": "total", "action": "approve"}
                    )
                    approved.raise_for_status()
                reviewed = client.get(root + "/report").json()
                rows = client.get(root + "/export.json?scope=reviewed").json()
                assert len(rows) == 1 and rows[0]["field"] == "total"
                if mode != "native":
                    assert all(row["text_mode"] == mode and "text_source" in row for row in rows)
                if name == "saved-form":
                    assert rows[0]["value"] == 100 and rows[0]["original_value"] == 900
                    assert (
                        rows[0]["verification_status"] == "needs_review"
                        and rows[0]["value_source"] == "correction"
                    )
                exports = {}
                for extension in ["json", "csv", "xlsx"]:
                    exported = client.get(root + f"/export.{extension}?scope=reviewed")
                    exported.raise_for_status()
                    (target / f"reviewed.{extension}").write_bytes(exported.content)
                    exports[extension] = {
                        "bytes": len(exported.content),
                        "sha256": sha(exported.content),
                    }
                archive = client.get(root + "/archive")
                archive.raise_for_status()
                (target / "review.zip").write_bytes(archive.content)
                with zipfile.ZipFile(io.BytesIO(archive.content)) as saved:
                    manifest = json.loads(saved.read("manifest.json"))
                    assert saved.read("document.pdf") == pdf.read_bytes()
                assert manifest["version"] == (1 if mode == "native" else 2)
                if mode != "native":
                    assert manifest["processing"] == {"text_mode": mode}
                store._sessions.clear()  # A new in-memory session store, as after restart.
                restored = client.post(
                    "/api/archives", files={"file": ("review.zip", archive.content)}
                )
                restored.raise_for_status()
                assert restored.json()["extraction"] == reviewed
                restored_root = f"/api/documents/{restored.json()['document']['id']}"
                assert client.get(restored_root + "/export.json?scope=reviewed").json() == rows
                case.update(
                    exports=exports,
                    reviewedRows=rows,
                    archiveVersion=manifest["version"],
                    archiveSha256=sha(archive.content),
                    restoreExact=True,
                )
                result["cases"].append(case)
        store._sessions.clear()
        for name, mode, expected in [
            ("nine-pages.pdf", "native", 200),
            ("nine-pages.pdf", "ocr-all", 413),
            ("blank.pdf", "ocr-all", 422),
        ]:
            data = (STUDY / "fixtures" / name).read_bytes()
            response = client.post(
                "/api/documents", data={"text_mode": mode}, files={"file": (name, data)}
            )
            assert response.status_code == expected, response.json()
            result["cases"].append(
                {
                    "name": name,
                    "mode": mode,
                    "uploadStatus": response.status_code,
                    "body": response.json(),
                }
            )
    for path, expected in original_inputs.items():
        assert sha((ROOT / path).read_bytes()) == expected, path
    result["inputsUnchanged"] = original_inputs
    (args.out / "capture.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "cases": len(result["cases"]),
                "recognizerPages": sum(len(r.get("nativeReference", [])) for r in result["cases"]),
                "nativeWordsChecked": sum(
                    p["words"] for r in result["cases"] for p in r.get("nativeReference", [])
                ),
                "archivesRestored": sum(r.get("restoreExact", False) for r in result["cases"]),
                "demoWritten": args.demo,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
