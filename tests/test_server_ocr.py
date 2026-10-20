from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fieldproof.server.app import app
from fieldproof.server.archive import decode_archive
from fieldproof.server.store import store

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture(autouse=True)
def isolate_sessions():
    store._sessions.clear()
    yield
    assert not store._reservations
    store._sessions.clear()


def test_missing_page_choice_keeps_native_words_without_an_installed_engine(monkeypatch):
    monkeypatch.setenv("PATH", "/no-tesseract-here")
    with TestClient(app) as client:
        response = client.post(
            "/api/documents",
            data={"text_mode": "ocr-missing"},
            files={"file": ("invoice.pdf", (EXAMPLES / "invoice.pdf").read_bytes())},
        )
        assert response.status_code == 200, response.json()
        document = response.json()
        assert document["text_mode"] == "ocr-missing"
        assert "ocr" not in document
        root = f"/api/documents/{document['id']}"
        extraction = client.post(
            root + "/extract",
            data={"schema": "invoice", "provider": "fixture"},
            files={"fixture": ("invoice.json", (EXAMPLES / "fixtures/invoice.json").read_bytes())},
        )
        assert extraction.status_code == 200
        assert extraction.json()["text_mode"] == "ocr-missing"
        rows = client.get(root + "/export.json").json()
        assert rows and all(r["text_mode"] == "ocr-missing" for r in rows)
        assert all(r["text_source"] in {"Native PDF text", "Unlocated evidence"} for r in rows)
        csv = client.get(root + "/export.csv")
        assert "text_mode,text_source" in csv.text.splitlines()[0]
        saved = client.get(root + "/archive")
        assert saved.status_code == 200
        archived = decode_archive(saved.content)
        assert archived.text_mode == "ocr-missing"
        with zipfile.ZipFile(io.BytesIO(saved.content)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        assert manifest["version"] == 2
        assert manifest["processing"] == {"text_mode": "ocr-missing"}
        restored = client.post("/api/archives", files={"file": ("review.zip", saved.content)})
        assert restored.status_code == 200, restored.json()
        assert restored.json()["document"]["text_mode"] == "ocr-missing"
        assert "ocr" not in restored.json()["extraction"]["report"]
        assert client.get(root + "/export.json").json() == rows


def test_unavailable_ocr_and_invalid_choices_preserve_the_existing_review(monkeypatch):
    monkeypatch.setenv("PATH", "/no-tesseract-here")
    content = (EXAMPLES / "invoice.pdf").read_bytes()
    with TestClient(app) as client:
        native = client.post("/api/documents", files={"file": ("invoice.pdf", content)})
        assert native.status_code == 200
        for mode, expected in [("ocr-all", 503), ("invented", 422)]:
            response = client.post(
                "/api/documents", data={"text_mode": mode}, files={"file": ("invoice.pdf", content)}
            )
            assert response.status_code == expected
            if expected == 503:
                assert "Tesseract" in response.json()["detail"]
            assert [d["id"] for d in client.get("/api/documents").json()["documents"]] == [
                native.json()["id"]
            ]


def test_native_archives_keep_the_existing_version_one_contract():
    with TestClient(app) as client:
        doc = client.post(
            "/api/documents",
            files={"file": ("invoice.pdf", (EXAMPLES / "invoice.pdf").read_bytes())},
        ).json()
        root = f"/api/documents/{doc['id']}"
        client.post(
            root + "/extract",
            data={"schema": "invoice", "provider": "fixture"},
            files={"fixture": ("invoice.json", (EXAMPLES / "fixtures/invoice.json").read_bytes())},
        ).raise_for_status()
        saved = client.get(root + "/archive").content
        with zipfile.ZipFile(io.BytesIO(saved)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["version"] == 1 and "processing" not in manifest
            assert (
                manifest["sha256"]["document.pdf"]
                == hashlib.sha256(archive.read("document.pdf")).hexdigest()
            )
        assert decode_archive(saved).text_mode == "native"
