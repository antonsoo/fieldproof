from __future__ import annotations

import hashlib
import importlib
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
def clear_store():
    store._sessions.clear()
    yield
    assert not store._reservations
    store._sessions.clear()


@pytest.fixture(scope="module")
def archive_bytes():
    with TestClient(app) as client:
        uploaded = client.post(
            "/api/documents",
            files={
                "file": ("invoice.pdf", (EXAMPLES / "invoice.pdf").read_bytes()),
            },
        )
        assert uploaded.status_code == 200
        root = f"/api/documents/{uploaded.json()['id']}"
        extracted = client.post(
            root + "/extract",
            data={"schema": "invoice", "provider": "fixture"},
            files={"fixture": ("fixture.json", (EXAMPLES / "fixtures/invoice.json").read_bytes())},
        )
        assert extracted.status_code == 200
        for path, action, value in [
            ("vendor_name", "approve", None),
            ("invoice_number", "edit", "00042 = literal\n日本語"),
            ("po_number", "edit", "rejected correction retained"),
            ("po_number", "reject", None),
            ("total", "edit", -0.25),
        ]:
            assert (
                client.post(
                    root + "/review", json={"path": path, "action": action, "value": value}
                ).status_code
                == 200
            )
        response = client.get(root + "/archive")
        assert response.status_code == 200
        assert response.content == client.get(root + "/archive").content
        store._sessions.clear()
        return response.content


def members_of(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def pack(members, *, update_hashes=True, compression=zipfile.ZIP_STORED):
    if update_hashes:
        manifest = json.loads(members["manifest.json"])
        manifest["sha256"] = {
            name: hashlib.sha256(members[name]).hexdigest()
            for name in ["document.pdf", "extraction.json", "review.json"]
        }
        members["manifest.json"] = json.dumps(manifest).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return output.getvalue()


def restore(client, content):
    return client.post("/api/archives", files={"file": ("renamed.zip", content, "application/zip")})


def test_archive_restores_all_decisions_and_original_claims_without_provider(
    archive_bytes, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("Restore must not call a provider")

    server = importlib.import_module("fieldproof.server.app")
    monkeypatch.setattr(server, "AnthropicExtractor", forbidden)
    with TestClient(app) as client:
        response = restore(client, archive_bytes)
        assert response.status_code == 200, response.text
        assert response.json()["document"]["restored_from_archive"] is True
        root = f"/api/documents/{response.json()['document']['id']}"
        result = client.get(root + "/report").json()
        assert result["provider"] == "fixture"
        assert result["review"]["invoice_number"] == {
            "status": "edited",
            "edited_value": "00042 = literal\n日本語",
        }
        assert result["review"]["po_number"] == {
            "status": "rejected",
            "edited_value": "rejected correction retained",
        }
        assert result["review"]["issue_date"] == {"status": "pending", "edited_value": None}
        assert result["review"]["vendor_name"] == {"status": "approved", "edited_value": None}
        original = next(field for field in result["report"]["fields"] if field["path"] == "total")
        assert original["value"] != -0.25
        assert result["data"]["total"]["value"] == original["value"]
        assert result["review"]["total"]["edited_value"] == -0.25
        assert client.get(root + "/pages/1.png").status_code == 200
        assert client.get(root + "/archive").content == archive_bytes
        # Rejected corrections can be reset after restore, without rewriting claims.
        assert (
            client.post(root + "/review", json={"path": "po_number", "action": "reset"}).status_code
            == 200
        )
        reset = client.get(root + "/report").json()
        assert reset["report"] == result["report"]
        assert reset["review"]["po_number"] == {"status": "pending", "edited_value": None}


@pytest.mark.parametrize(
    "case",
    [
        "not_zip",
        "truncated",
        "extra_member",
        "traversal",
        "checksum",
        "version",
        "boolean_version",
        "missing_decision",
        "extra_decision",
        "wrong_scalar",
        "pending_correction",
        "edited_null",
        "unknown_status",
        "extra_claim",
        "missing_claim",
        "coerced_claim",
        "duplicate_key",
        "nonfinite",
        "surrogate",
        "deep_json",
        "bad_pdf",
        "large_pdf",
        "large_review",
        "correction_budget",
    ],
)
def test_malformed_archive_is_atomic(archive_bytes, case):
    members = members_of(archive_bytes)
    review = json.loads(members["review.json"])
    data = json.loads(members["extraction.json"])
    manifest = json.loads(members["manifest.json"])
    if case in {"version", "boolean_version"}:
        manifest["version"] = 2 if case == "version" else True
        members["manifest.json"] = json.dumps(manifest).encode()
    if case == "extra_member":
        members["report.json"] = b'{"counts":{"verified":999}}'
    if case == "traversal":
        members["../document.pdf"] = members.pop("document.pdf")
    if case == "checksum":
        members["document.pdf"] += b"\nchanged"
    if case == "missing_decision":
        del review["total"]
    if case == "extra_decision":
        review["made_up"] = {"status": "approved", "edited_value": None}
    if case == "wrong_scalar":
        review["total"]["edited_value"] = True
    if case == "pending_correction":
        review["total"]["status"] = "pending"
    if case == "edited_null":
        review["total"]["edited_value"] = None
    if case == "unknown_status":
        review["total"]["status"] = "verified"
    if case == "correction_budget":
        review["invoice_number"]["edited_value"] = "x" * (1024 * 1024)
    if case == "extra_claim":
        data["ignored"] = {"value": "not retained", "evidence": []}
    if case == "missing_claim":
        del data["currency"]
    if case == "coerced_claim":
        data["total"]["value"] = str(data["total"]["value"])
    members["review.json"] = json.dumps(review).encode()
    members["extraction.json"] = json.dumps(data).encode()
    if case == "duplicate_key":
        members["review.json"] = b'{"total":{},"total":{}}'
    if case == "nonfinite":
        members["review.json"] = b'{"total":{"status":"edited","edited_value":1e999}}'
    if case == "surrogate":
        members["review.json"] = b'{"bad":"\\ud800"}'
    if case == "deep_json":
        members["review.json"] = b'{"bad":' + b"[" * 1500 + b"0" + b"]" * 1500 + b"}"
    if case == "bad_pdf":
        members["document.pdf"] = b"This is not a PDF"
    if case == "large_pdf":
        members["document.pdf"] = b"x" * (25 * 1024 * 1024 + 1)
    if case == "large_review":
        members["review.json"] = b" " * (2 * 1024 * 1024 + 1)
    content = pack(
        members,
        update_hashes=case not in {"checksum", "traversal"},
        compression=zipfile.ZIP_DEFLATED,
    )
    if case == "not_zip":
        content = b"not zip"
    if case == "truncated":
        content = content[:-100]
    with TestClient(app) as client:
        existing = restore(client, archive_bytes).json()["document"]
        root = f"/api/documents/{existing['id']}"
        report = client.get(root + "/report").json()
        response = restore(client, content)
        assert response.status_code == (
            413 if case in {"large_pdf", "large_review", "correction_budget"} else 422
        ), response.text
        assert len(client.get("/api/documents").json()["documents"]) == 1
        assert client.get(root + "/report").json() == report


def test_duplicate_zip_members_rejected(archive_bytes):
    buffer = io.BytesIO(archive_bytes)
    with zipfile.ZipFile(buffer, "a") as archive, pytest.warns(UserWarning, match="Duplicate name"):
        archive.writestr("document.pdf", b"wrong PDF")
    with pytest.raises(ValueError, match="exactly"):
        decode_archive(buffer.getvalue())


def test_restore_capacity_and_busy_export_preserve_session(archive_bytes, monkeypatch):
    with TestClient(app) as client:
        restored = restore(client, archive_bytes).json()["document"]
        monkeypatch.setattr(store, "max_sessions", 1)
        assert restore(client, archive_bytes).status_code == 409
        session = store.get(restored["id"])
        assert session is not None
        with store.extracting(session):
            assert client.get(f"/api/documents/{session.id}/archive").status_code == 409
        assert client.get(f"/api/documents/{session.id}/archive").content == archive_bytes


def test_archive_recomputes_verification(archive_bytes, monkeypatch):
    server = importlib.import_module("fieldproof.server.app")
    original_verify = server.verify_server_data
    calls = []

    def verify_again(schema, data, document):
        calls.append(schema)
        report = original_verify(schema, data, document)
        report.fields[0].reasons.append("Sentinel: this verifier actually ran on restore")
        return report

    monkeypatch.setattr(server, "verify_server_data", verify_again)
    with TestClient(app) as client:
        restored = restore(client, archive_bytes).json()["document"]
        report = client.get(f"/api/documents/{restored['id']}/report").json()
        assert calls == ["invoice"]
        assert (
            "Sentinel: this verifier actually ran on restore"
            in report["report"]["fields"][0]["reasons"]
        )


def test_empty_model_identifier_round_trips(archive_bytes):
    members = members_of(archive_bytes)
    manifest = json.loads(members["manifest.json"])
    manifest["model"] = ""
    members["manifest.json"] = json.dumps(manifest).encode()
    assert decode_archive(pack(members)).extraction.model == ""


def test_deflated_archive_preserves_content(archive_bytes):
    compressed = pack(members_of(archive_bytes), compression=zipfile.ZIP_DEFLATED)
    assert len(compressed) < len(archive_bytes)
    with TestClient(app) as client:
        restored = restore(client, compressed)
        assert restored.status_code == 200, restored.text
        archived = client.get(f"/api/documents/{restored.json()['document']['id']}/archive")
        assert archived.content == archive_bytes


def test_archive_request_size_is_rejected_before_multipart_decode():
    with TestClient(app) as client:
        response = client.post(
            "/api/archives",
            content=b"small",
            headers={
                "Content-Length": str(31 * 1024 * 1024 + 1),
                "Content-Type": "multipart/form-data; boundary=not-parsed",
            },
        )
        assert response.status_code == 413
        assert not store.list()
