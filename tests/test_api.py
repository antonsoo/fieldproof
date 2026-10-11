from __future__ import annotations

import csv
import io
import json
from pathlib import Path

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


def test_repeated_amount_invoice_fits_existing_worker_budget_and_keeps_ambiguity(client):
    fixtures = Path(__file__).resolve().parents[1] / "studies/grounding-reuse/fixtures"
    uploaded = client.post(
        "/api/documents",
        files={
            "file": ("rows-100.pdf", (fixtures / "rows-100.pdf").read_bytes(), "application/pdf"),
        },
    )
    assert uploaded.status_code == 200
    document_id = uploaded.json()["id"]
    response = client.post(
        f"/api/documents/{document_id}/extract",
        data={
            "schema": "invoice",
            "provider": "fixture",
        },
        files={
            "fixture": (
                "rows-100.json",
                (fixtures / "rows-100.json").read_bytes(),
                "application/json",
            ),
        },
    )
    assert response.status_code == 200, response.text
    report = response.json()["report"]
    assert report["counts"] == {"verified": 201, "needs_review": 203, "unsupported": 0}
    assert len(report["fields"]) == 404
    fields = {field["path"]: field for field in report["fields"]}
    for index in (0, 49, 50, 99):
        quantity = fields[f"line_items[{index}].quantity"]
        assert quantity["status"] == "verified" and quantity["value"] == 1
        assert quantity["matched_text"] == "1" and quantity["page"] == index // 50 + 1
        amount = fields[f"line_items[{index}].amount"]
        assert amount["status"] == "needs_review" and amount["rects"] == []
        assert "ambiguous (appears 200 times)" in amount["reasons"][0]
    assert client.get(f"/api/documents/{document_id}/report").json()["report"] == report


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
    checks = body["report"]["cross_field_checks"]
    assert [c["status"] for c in checks] == ["not_checked", "passed", "not_checked"]
    assert checks[1]["computed"] == "110"
    assert checks[1]["difference"] == "0"
    assert checks[1]["operands"] == {"subtotal": "100.0", "tax": "10.0", "total": "110.0"}

    r2 = client.get(f"/api/documents/{doc_id}/report")
    assert r2.status_code == 200
    assert r2.json()["report"]["counts"]["verified"] == 6
    assert r2.json()["report"]["cross_field_checks"] == checks

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


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"{ not json", "extraction.json is not valid JSON"),
        (b"[1, 2]", "extraction.json must hold a JSON object, not list"),
        (b"\x80\x81 not text", "extraction.json is not UTF-8 text"),
        (b'{"data": {"total": "x"}}', "extraction.json does not match the Invoice schema"),
    ],
)
def test_extract_with_an_unusable_fixture_is_a_422_that_says_why(
    client: TestClient, simple_invoice_pdf_bytes: bytes, content: bytes, expected: str
) -> None:
    # Each of these was an unhandled exception: a bare 500 in the review UI.
    upload = client.post(
        "/api/documents",
        files={"file": ("invoice.pdf", io.BytesIO(simple_invoice_pdf_bytes), "application/pdf")},
    )
    doc_id = upload.json()["id"]
    r = client.post(
        f"/api/documents/{doc_id}/extract",
        data={"schema": "invoice", "provider": "fixture"},
        files={"fixture": ("extraction.json", io.BytesIO(content), "application/json")},
    )
    assert r.status_code == 422
    assert expected in r.json()["detail"]
    assert client.get(f"/api/documents/{doc_id}/report").status_code == 404  # nothing was stored


@pytest.fixture
def extracted_document(client, simple_invoice_pdf_bytes, fixture_bytes):
    document_id = client.post(
        "/api/documents",
        files={"file": ("invoice.pdf", simple_invoice_pdf_bytes, "application/pdf")},
    ).json()["id"]
    response = client.post(
        f"/api/documents/{document_id}/extract",
        data={"schema": "invoice", "provider": "fixture"},
        files={"fixture": ("fixture.json", fixture_bytes, "application/json")},
    )
    assert response.status_code == 200
    return document_id


def test_oversized_fixture_preserves_extraction_and_saved_decision(
    client,
    extracted_document,
    fixture_bytes,
):
    client.post(
        f"/api/documents/{extracted_document}/review",
        json={"path": "total", "action": "edit", "value": 123.5},
    )
    before = client.get(f"/api/documents/{extracted_document}/report").json()
    response = client.post(
        f"/api/documents/{extracted_document}/extract",
        data={"schema": "invoice", "provider": "fixture"},
        files={
            "fixture": ("large.json", fixture_bytes + b" " * (2 * 1024 * 1024), "application/json")
        },
    )
    assert response.status_code == 413
    assert client.get(f"/api/documents/{extracted_document}/report").json() == before
    assert not store.is_busy(extracted_document)


def test_excessive_field_count_does_not_replace_prior_review(
    client,
    extracted_document,
    fixture_bytes,
):
    client.post(
        f"/api/documents/{extracted_document}/review",
        json={"path": "total", "action": "approve"},
    )
    before = client.get(f"/api/documents/{extracted_document}/report").json()
    raw = json.loads(fixture_bytes)
    item = {
        "description": {"value": "Widget", "evidence": ["Widget"], "page": 1},
        "amount": {"value": 1.0, "evidence": ["Widget"], "page": 1},
    }
    raw["data"]["line_items"] = [item] * 1000
    response = client.post(
        f"/api/documents/{extracted_document}/extract",
        data={"schema": "invoice", "provider": "fixture"},
        files={"fixture": ("many.json", json.dumps(raw).encode(), "application/json")},
    )
    assert response.status_code == 413
    assert "2,000-field" in response.json()["detail"]
    assert client.get(f"/api/documents/{extracted_document}/report").json() == before


def test_excessive_correction_bytes_leave_prior_value_intact(client, extracted_document):
    from fieldproof.server.store import ReviewState

    session = store.get(extracted_document)
    # Simulate other reviewed fields near the total budget, then use a real
    # request that exceeds it. The target's original review must survive.
    session.review["invoice_number"] = ReviewState(status="edited", edited_value="x" * 1048500)
    before = session.review["vendor_name"]
    response = client.post(
        f"/api/documents/{extracted_document}/review",
        json={"path": "vendor_name", "action": "edit", "value": "y" * 100},
    )
    assert response.status_code == 413
    assert session.review["vendor_name"] is before


def test_verification_budget_failure_keeps_previous_review_and_allows_retry(
    client,
    extracted_document,
    fixture_bytes,
    monkeypatch,
):
    import importlib

    from fieldproof.document.limits import DocumentLimitError

    module = importlib.import_module("fieldproof.server.app")
    client.post(
        f"/api/documents/{extracted_document}/review",
        json={"path": "total", "action": "edit", "value": 123.5},
    )
    previous = client.get(f"/api/documents/{extracted_document}/report").json()
    original = module.verify_server_data

    def exhausted(*args):
        raise DocumentLimitError("Verification exceeded its resource budget")

    monkeypatch.setattr(module, "verify_server_data", exhausted)

    def extract_again():
        return client.post(
            f"/api/documents/{extracted_document}/extract",
            data={"schema": "invoice", "provider": "fixture"},
            files={"fixture": ("invoice.json", fixture_bytes, "application/json")},
        )

    assert extract_again().status_code == 413
    assert client.get(f"/api/documents/{extracted_document}/report").json() == previous
    assert not store.is_busy(extracted_document)
    monkeypatch.setattr(module, "verify_server_data", original)
    assert extract_again().status_code == 200


@pytest.mark.parametrize("value", [321.5, 0, -12.5])
def test_correction_retains_numeric_type_through_approve_reject_reset(
    client, extracted_document, value
):
    url = f"/api/documents/{extracted_document}"
    original_report = client.get(f"{url}/report").json()["report"]
    for action in ["edit", "approve", "reject", "approve"]:
        response = client.post(
            f"{url}/review", json={"path": "total", "action": action, "value": value}
        )
        assert response.status_code == 200
        assert response.json()["edited_value"] == value
        rows = client.get(f"{url}/export.json?scope=reviewed").json()
        if action == "reject":
            assert rows == []
        else:
            assert rows[0]["value"] == value
            assert isinstance(rows[0]["value"], (int, float))
    assert client.get(f"{url}/report").json()["report"] == original_report
    client.post(f"{url}/review", json={"path": "total", "action": "reset"})
    assert client.get(f"{url}/export.json?scope=reviewed").json() == []
    rows = {r["field"]: r for r in client.get(f"{url}/export.json").json()}
    assert rows["total"]["value"] == 110.0


@pytest.mark.parametrize("value", [None, "", "123.5", True, False, [], {}, 10**500])
def test_invalid_correction_does_not_change_decisions(client, extracted_document, value):
    url = f"/api/documents/{extracted_document}"
    before = client.get(f"{url}/report").json()
    response = client.post(
        f"{url}/review", json={"path": "total", "action": "edit", "value": value}
    )
    assert response.status_code == 422
    assert client.get(f"{url}/report").json() == before


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e309"])
def test_nonfinite_corrections_are_rejected(client, extracted_document, literal):
    response = client.post(
        f"/api/documents/{extracted_document}/review",
        content='{"path":"total","action":"edit","value":' + literal + "}",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422


def test_export_scopes_keep_review_and_verification_separate(client, extracted_document):
    url = f"/api/documents/{extracted_document}"
    assert client.get(f"{url}/export.json?scope=reviewed").json() == []
    value = '00034,\r\n"identifier"'
    client.post(f"{url}/review", json={"path": "invoice_number", "action": "edit", "value": value})
    client.post(f"{url}/review", json={"path": "invoice_number", "action": "approve"})
    rows = client.get(f"{url}/export.json?scope=reviewed").json()
    assert len(rows) == 1
    assert rows[0]["value"] == value
    assert rows[0]["original_value"] == "INV-1001"
    assert rows[0]["value_source"] == "correction"
    assert rows[0]["review_status"] == "approved"
    assert rows[0]["verification_status"] == "verified"  # original extraction's check
    csv_rows = list(
        csv.DictReader(io.StringIO(client.get(f"{url}/export.csv?scope=reviewed").text))
    )
    assert csv_rows[0]["value"] == value
    assert len(client.get(f"{url}/export.json?scope=all").json()) > 1
    assert client.get(f"{url}/export.json?scope=typo").status_code == 422


def test_source_build_wins_over_stale_packaged_ui_and_explicit_override_wins(tmp_path, monkeypatch):
    import importlib

    module = importlib.import_module("fieldproof.server.app")
    source = tmp_path / "checkout"
    server = source / "src" / "fieldproof" / "server"
    server.mkdir(parents=True)
    monkeypatch.setattr(module, "__file__", str(server / "app.py"))
    monkeypatch.delenv("FIELDPROOF_STATIC_DIR", raising=False)
    bundled = server / "static"
    bundled.mkdir()
    (bundled / "index.html").write_text("older packaged UI")
    fresh = source / "web" / "dist"
    fresh.mkdir(parents=True)
    (fresh / "index.html").write_text("fresh source UI")
    (source / "pyproject.toml").write_text('[project]\nname="fieldproof"\n')
    assert module._find_static_dir() == fresh
    (source / "pyproject.toml").unlink()  # installed wheel has no source checkout
    assert module._find_static_dir() == bundled
    override = tmp_path / "override"
    monkeypatch.setenv("FIELDPROOF_STATIC_DIR", str(override))
    assert module._find_static_dir() == override


def test_boolean_review_preserves_false_through_approval_and_both_export_formats(
    client, extracted_document
):
    from fieldproof.server.store import ReviewState
    from fieldproof.verify.engine import FieldStatus, FieldVerification

    session = store.get(extracted_document)
    assert session is not None and session.report is not None
    session.report.fields.append(FieldVerification("agreed", True, FieldStatus.VERIFIED))
    session.review["agreed"] = ReviewState()
    url = f"/api/documents/{extracted_document}"
    for invalid in ["false", 0, None]:
        assert (
            client.post(
                f"{url}/review", json={"path": "agreed", "action": "edit", "value": invalid}
            ).status_code
            == 422
        )
    for action in ["edit", "approve"]:
        response = client.post(
            f"{url}/review", json={"path": "agreed", "action": action, "value": False}
        )
        assert response.json()["edited_value"] is False
    rows = client.get(f"{url}/export.json?scope=reviewed").json()
    assert rows[0]["value"] is False
    assert rows[0]["original_value"] is True
    csv_rows = list(
        csv.DictReader(io.StringIO(client.get(f"{url}/export.csv?scope=reviewed").text))
    )
    assert csv_rows[0]["value"] == "false"
    assert csv_rows[0]["original_value"] == "true"
