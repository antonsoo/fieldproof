from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from fieldproof.server.app import app
from fieldproof.server.store import store


@pytest.fixture(autouse=True)
def _clear_store():
    # The store is a process-wide singleton by design (see store.py); reset
    # it between tests so they don't see each other's documents.
    store._sessions.clear()
    yield
    store._sessions.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def fixture_bytes() -> bytes:
    payload = {
        "schema": "Invoice",
        "model": "fixture-v1",
        "data": {
            "vendor_name": {
                "value": "Acme Corporation",
                "evidence": ["Acme Corporation"],
                "page": 1,
            },
            "invoice_number": {
                "value": "INV-1001",
                "evidence": ["Invoice Number: INV-1001"],
                "page": 1,
            },
            "issue_date": {
                "value": "2026-01-01",
                "evidence": ["Issue Date: January 1, 2026"],
                "page": 1,
            },
            "total": {"value": 110.0, "evidence": ["Total: $110.00"], "page": 1},
            "subtotal": {"value": 100.0, "evidence": ["Subtotal: $100.00"], "page": 1},
            "tax": {"value": 10.0, "evidence": ["Tax: $10.00"], "page": 1},
            "line_items": [],
        },
    }
    return json.dumps(payload).encode("utf-8")


def test_list_schemas(client: TestClient) -> None:
    r = client.get("/api/schemas")
    assert r.status_code == 200
    assert set(r.json()["schemas"]) == {"invoice", "receipt", "contract"}


def test_upload_document(client: TestClient, simple_invoice_pdf_bytes: bytes) -> None:
    r = client.post(
        "/api/documents",
        files={"file": ("invoice.pdf", io.BytesIO(simple_invoice_pdf_bytes), "application/pdf")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["page_count"] == 1
    assert body["filename"] == "invoice.pdf"


def test_upload_rejects_non_pdf(client: TestClient) -> None:
    r = client.post(
        "/api/documents", files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")}
    )
    assert r.status_code == 422


def test_get_page_image(client: TestClient, simple_invoice_pdf_bytes: bytes) -> None:
    upload = client.post(
        "/api/documents",
        files={"file": ("invoice.pdf", io.BytesIO(simple_invoice_pdf_bytes), "application/pdf")},
    )
    doc_id = upload.json()["id"]
    r = client.get(f"/api/documents/{doc_id}/pages/1.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_extract_with_fixture_provider_and_review_flow(
    client: TestClient, simple_invoice_pdf_bytes: bytes, fixture_bytes: bytes
) -> None:
    upload = client.post(
        "/api/documents",
        files={"file": ("invoice.pdf", io.BytesIO(simple_invoice_pdf_bytes), "application/pdf")},
    )
    doc_id = upload.json()["id"]

    r = client.post(
        f"/api/documents/{doc_id}/extract",
        data={"schema": "invoice", "provider": "fixture"},
        files={"fixture": ("fixture.json", io.BytesIO(fixture_bytes), "application/json")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["report"]["counts"]["verified"] == 6

    r2 = client.get(f"/api/documents/{doc_id}/report")
    assert r2.status_code == 200
    assert r2.json()["report"]["counts"]["verified"] == 6

    review = client.post(
        f"/api/documents/{doc_id}/review", json={"path": "total", "action": "approve"}
    )
    assert review.status_code == 200
    assert review.json()["status"] == "approved"

    edit = client.post(
        f"/api/documents/{doc_id}/review",
        json={"path": "vendor_name", "action": "edit", "value": "Acme Corp Inc."},
    )
    assert edit.status_code == 200
    assert edit.json()["edited_value"] == "Acme Corp Inc."

    export_json = client.get(f"/api/documents/{doc_id}/export.json")
    assert export_json.status_code == 200
    rows = {row["field"]: row for row in export_json.json()}
    assert rows["vendor_name"]["value"] == "Acme Corp Inc."
    assert rows["total"]["review_status"] == "approved"

    export_csv = client.get(f"/api/documents/{doc_id}/export.csv")
    assert export_csv.status_code == 200
    assert "vendor_name" in export_csv.text


def test_extract_requires_fixture_file_for_fixture_provider(
    client: TestClient, simple_invoice_pdf_bytes: bytes
) -> None:
    upload = client.post(
        "/api/documents",
        files={"file": ("invoice.pdf", io.BytesIO(simple_invoice_pdf_bytes), "application/pdf")},
    )
    doc_id = upload.json()["id"]
    r = client.post(
        f"/api/documents/{doc_id}/extract", data={"schema": "invoice", "provider": "fixture"}
    )
    assert r.status_code == 400


def test_extract_anthropic_without_api_key_returns_clear_error(
    client: TestClient, simple_invoice_pdf_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    upload = client.post(
        "/api/documents",
        files={"file": ("invoice.pdf", io.BytesIO(simple_invoice_pdf_bytes), "application/pdf")},
    )
    doc_id = upload.json()["id"]
    r = client.post(
        f"/api/documents/{doc_id}/extract", data={"schema": "invoice", "provider": "anthropic"}
    )
    assert r.status_code == 400
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_unknown_document_returns_404(client: TestClient) -> None:
    r = client.get("/api/documents/does-not-exist")
    assert r.status_code == 404
