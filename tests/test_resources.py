from __future__ import annotations

import asyncio
import io
import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from starlette.exceptions import HTTPException

from fieldproof.document.limits import DocumentLimitError, DocumentLimits, check_page_pixels
from fieldproof.document.loader import load_pdf
from fieldproof.document.render import render_page_png
from fieldproof.server.app import app
from fieldproof.server.body_limit import BodyLimitMiddleware
from fieldproof.server.pdf_work import load_server_pdf
from fieldproof.server.store import DocumentStore, SessionBusyError, StoreCapacityError, store


@pytest.fixture(autouse=True)
def clear_store():
    store._sessions.clear()
    yield
    assert not store._reservations
    assert not store._busy
    store._sessions.clear()


def upload(client, pdf):
    return client.post("/api/documents", files={"file": ("invoice.pdf", pdf, "application/pdf")})


def test_store_refuses_new_sessions_without_evicting_decisions(simple_invoice_pdf_bytes):
    local = DocumentStore(max_sessions=1)
    document = load_pdf(simple_invoice_pdf_bytes)
    first = local.create("one.pdf", simple_invoice_pdf_bytes, document)
    with pytest.raises(StoreCapacityError, match="slots"):
        local.create("two.pdf", simple_invoice_pdf_bytes, document)
    assert local.get(first.id) is first
    assert local.delete(first.id)
    assert not local.delete(first.id)
    assert local.create("two.pdf", simple_invoice_pdf_bytes, document).filename == "two.pdf"


@pytest.mark.parametrize("budget", ["bytes", "words"])
def test_retained_content_budgets(simple_invoice_pdf_bytes, budget):
    document = load_pdf(simple_invoice_pdf_bytes)
    kwargs = (
        {"max_pdf_bytes": len(simple_invoice_pdf_bytes)}
        if budget == "bytes"
        else {"max_words": sum(len(page.words) for page in document.pages)}
    )
    local = DocumentStore(**kwargs)
    first = local.create("one.pdf", simple_invoice_pdf_bytes, document)
    with pytest.raises(StoreCapacityError):
        local.create("two.pdf", simple_invoice_pdf_bytes, document)
    assert local.list() == [first]
    local.delete(first.id)
    assert local.create("three.pdf", simple_invoice_pdf_bytes, document)


def test_upload_reservation_releases_on_failure_and_blocks_concurrent_load():
    local = DocumentStore(max_pending_uploads=1)
    with pytest.raises(ValueError, match="bad PDF"), local.reserve_upload(10):
        with pytest.raises(SessionBusyError), local.reserve_upload(10):
            pytest.fail("concurrent PDF work was admitted")
        raise ValueError("bad PDF")
    assert local._reservations == {}
    with local.reserve_upload(10):
        assert len(local._reservations) == 1
    assert local._reservations == {}


def test_extraction_lease_refuses_deletion_and_concurrent_reextraction(simple_invoice_pdf_bytes):
    local = DocumentStore()
    first = local.create("one.pdf", simple_invoice_pdf_bytes, load_pdf(simple_invoice_pdf_bytes))
    with local.extracting(first):
        assert local.is_busy(first.id)
        with pytest.raises(SessionBusyError):
            local.delete(first.id)
        with pytest.raises(SessionBusyError), local.extracting(first):
            pytest.fail("parallel extraction admitted")
    assert not local.is_busy(first.id)
    assert local.delete(first.id)
    with pytest.raises(KeyError), local.extracting(first):
        pytest.fail("deleted session resurrected")


def test_session_api_lists_reopens_deletes_and_reclaims_capacity(
    simple_invoice_pdf_bytes, monkeypatch
):
    monkeypatch.setattr(store, "max_sessions", 1)
    with TestClient(app) as client:
        first = upload(client, simple_invoice_pdf_bytes).json()
        listing = client.get("/api/documents").json()
        assert listing["max_sessions"] == 1
        assert listing["documents"] == [first]
        assert first["reviewed_count"] == 0
        assert first["has_extraction"] is False
        assert upload(client, simple_invoice_pdf_bytes).status_code == 409
        assert client.get(f"/api/documents/{first['id']}").json() == first
        assert client.delete(f"/api/documents/{first['id']}").status_code == 204
        assert client.get(f"/api/documents/{first['id']}").status_code == 404
        assert client.get(f"/api/documents/{first['id']}/pages/1.png").status_code == 404
        assert upload(client, simple_invoice_pdf_bytes).status_code == 200


def test_busy_session_api_keeps_document(simple_invoice_pdf_bytes):
    with TestClient(app) as client:
        first = upload(client, simple_invoice_pdf_bytes).json()
        session = store.get(first["id"])
        with store.extracting(session):
            assert client.get("/api/documents").json()["documents"][0]["busy"] is True
            assert client.delete(f"/api/documents/{first['id']}").status_code == 409
            assert (
                client.post(
                    f"/api/documents/{first['id']}/extract",
                    data={"schema": "invoice"},
                ).status_code
                == 409
            )
            assert (
                client.post(
                    f"/api/documents/{first['id']}/review",
                    json={"path": "total", "action": "approve"},
                ).status_code
                == 409
            )
        assert client.get(f"/api/documents/{first['id']}").status_code == 200


def test_oversized_file_rejected_before_loading_and_next_upload_works(
    simple_invoice_pdf_bytes,
    monkeypatch,
):
    # Import the module explicitly: server.__init__ also exports an app object.
    import importlib

    app_module = importlib.import_module("fieldproof.server.app")
    monkeypatch.setattr(app_module, "MAX_PDF_BYTES", len(simple_invoice_pdf_bytes))
    with TestClient(app) as client:
        assert upload(client, simple_invoice_pdf_bytes + b"x").status_code == 413
        assert client.get("/api/documents").json()["documents"] == []
        assert upload(client, simple_invoice_pdf_bytes).status_code == 200


def test_request_length_rejected_without_consuming_body():
    received = False
    responses = []

    async def inner(*args):
        pytest.fail("oversized request reached application")

    async def receive():
        nonlocal received
        received = True
        return {"type": "http.request", "body": b""}

    async def send(message):
        responses.append(message)

    asyncio.run(
        BodyLimitMiddleware(inner)(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/documents",
                "headers": [(b"content-length", b"1000000000")],
            },
            receive,
            send,
        )
    )
    assert not received
    assert responses[0]["status"] == 413


def test_chunked_body_stops_at_budget_without_reading_later_chunks():
    chunks = iter([b"a" * 40_000, b"b" * 40_000, b"never-read"])
    seen = []

    async def inner(scope, receive, send):
        while True:
            message = await receive()
            seen.append(message["body"])

    async def receive():
        return {"type": "http.request", "body": next(chunks), "more_body": True}

    async def send(message):
        pytest.fail("unexpected response")

    with pytest.raises(HTTPException) as failure:
        asyncio.run(
            BodyLimitMiddleware(inner)(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/api/documents/x/review",
                    "headers": [],
                },
                receive,
                send,
            )
        )
    assert failure.value.status_code == 413
    assert len(seen) == 1
    assert next(chunks) == b"never-read"


@pytest.mark.parametrize(
    "limits, message",
    [
        (replace(DocumentLimits(), max_pages=1), "pages"),
        (replace(DocumentLimits(), max_words=1), "word"),
        (replace(DocumentLimits(), max_text_chars=1), "character"),
    ],
)
def test_document_content_budgets(two_page_pdf_bytes, limits, message):
    with pytest.raises(DocumentLimitError, match=message):
        load_pdf(two_page_pdf_bytes, limits=limits)


@pytest.mark.parametrize(
    "width,height,scale",
    [
        (0, 100, 2),
        (-1, 100, 2),
        (float("inf"), 1, 2),
        (1, float("nan"), 2),
        (1, 1, 0),
    ],
)
def test_invalid_dimensions_are_refused(width, height, scale):
    with pytest.raises(DocumentLimitError):
        check_page_pixels(width, height, scale, 16_000_000)


def test_huge_page_refused_before_rendering():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(5000, 5000))
    pdf.drawString(20, 20, "Large page")
    pdf.save()
    content = buffer.getvalue()
    with pytest.raises(DocumentLimitError, match="pixel"):
        load_server_pdf(content, "huge.pdf")
    with pytest.raises(DocumentLimitError, match="pixel"):
        render_page_png(content, 1, max_pixels=16_000_000)


def test_worker_timeout_cleans_up_and_is_recoverable(simple_invoice_pdf_bytes, monkeypatch):
    from fieldproof.server import pdf_work

    original = pdf_work.subprocess.run
    paths = []

    def timeout(command, **kwargs):
        paths.append(Path(command[5]))
        raise subprocess.TimeoutExpired(command, 30)

    monkeypatch.setattr(pdf_work.subprocess, "run", timeout)
    with pytest.raises(DocumentLimitError, match="time limit"):
        load_server_pdf(simple_invoice_pdf_bytes, "invoice.pdf")
    assert all(not path.exists() for path in paths)
    monkeypatch.setattr(pdf_work.subprocess, "run", original)
    assert load_server_pdf(simple_invoice_pdf_bytes, "invoice.pdf").page_count == 1


def test_malformed_pdf_does_not_leak_reservation_or_session(simple_invoice_pdf_bytes):
    with TestClient(app) as client:
        assert upload(client, b"not a PDF").status_code == 422
        assert not store._sessions
        assert not store._reservations
        assert upload(client, simple_invoice_pdf_bytes).status_code == 200


def test_too_many_pages_rejected_by_real_worker_before_text_parsing():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for number in range(65):
        pdf.drawString(20, 20, f"Page {number}")
        pdf.showPage()
    pdf.save()
    with TestClient(app) as client:
        response = upload(client, buffer.getvalue())
        assert response.status_code == 413
        assert "64 pages" in response.json()["detail"]
        assert not store._sessions


def test_image_only_pdf_has_clear_error_and_preserves_previous_session(simple_invoice_pdf_bytes):
    from PIL import Image
    from reportlab.lib.utils import ImageReader

    image = Image.new("RGB", (200, 200), color="white")
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawImage(ImageReader(image), 20, 20, width=200, height=200)
    pdf.save()
    with TestClient(app) as client:
        previous = upload(client, simple_invoice_pdf_bytes).json()
        response = upload(client, buffer.getvalue())
        assert response.status_code == 422
        assert "text layer" in response.json()["detail"]
        assert client.get("/api/documents").json()["documents"] == [previous]


def test_actual_api_handles_chunked_body_overflow():
    with TestClient(app) as client:
        response = client.post(
            "/api/documents/x/review",
            headers={"Content-Type": "application/json"},
            content=iter([b'{"path":"', b"x" * 70000, b'"}']),
        )
        assert response.status_code == 413
        assert not store._sessions


def test_request_concurrency_is_bounded_and_slots_released():
    async def scenario():
        gate = asyncio.Event()
        entered = 0
        responses = []

        async def inner(scope, receive, send):
            nonlocal entered
            entered += 1
            await gate.wait()

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            responses.append(message)

        middleware = BodyLimitMiddleware(inner)
        scope = {"type": "http", "method": "POST", "path": "/api/documents", "headers": []}
        admitted = [asyncio.create_task(middleware(scope, receive, send)) for _ in range(4)]
        await asyncio.sleep(0)
        assert entered == 4
        await middleware(scope, receive, send)
        assert responses[0]["status"] == 503
        gate.set()
        await asyncio.gather(*admitted)
        await middleware(scope, receive, send)
        assert entered == 5

    asyncio.run(scenario())


def test_two_uploads_are_admitted_but_backlog_is_bounded():
    local = DocumentStore()
    with (
        local.reserve_upload(10),
        local.reserve_upload(10),
        pytest.raises(SessionBusyError),
        local.reserve_upload(10),
    ):
        pytest.fail("third pending upload admitted")
    assert not local._reservations


def test_worker_backlog_is_bounded_and_reservation_released(simple_invoice_pdf_bytes):
    from fieldproof.server import pdf_work

    for _ in range(4):
        assert pdf_work._worker_slots.acquire(blocking=False)
    try:
        with pytest.raises(pdf_work.PdfWorkerBusyError, match="busy"):
            load_server_pdf(simple_invoice_pdf_bytes, "invoice.pdf")
    finally:
        for _ in range(4):
            pdf_work._worker_slots.release()
    assert load_server_pdf(simple_invoice_pdf_bytes, "invoice.pdf").page_count == 1


@pytest.mark.skipif(sys.platform != "linux", reason="Linux worker resource enforcement")
def test_worker_enforces_address_space_cpu_and_output_limits():
    script = """
import json, resource
from fieldproof.document.worker import _set_process_limits
_set_process_limits()
print(json.dumps([resource.getrlimit(key) for key in (
    resource.RLIMIT_AS, resource.RLIMIT_CPU, resource.RLIMIT_FSIZE)]))
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, check=True, text=True
    )
    assert json.loads(result.stdout) == [
        [768 * 1024 * 1024] * 2,
        [20, 20],
        [64 * 1024 * 1024] * 2,
    ]


def test_slow_pdf_work_keeps_api_responsive_and_cannot_overfill_store(
    simple_invoice_pdf_bytes,
    monkeypatch,
):
    import importlib

    module = importlib.import_module("fieldproof.server.app")
    document = load_pdf(simple_invoice_pdf_bytes)
    entered = threading.Event()
    release = threading.Event()

    def slow_load(*args):
        entered.set()
        assert release.wait(timeout=5)
        return document

    monkeypatch.setattr(module, "load_server_pdf", slow_load)
    monkeypatch.setattr(store, "max_sessions", 1)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(upload, client, simple_invoice_pdf_bytes)
        try:
            assert entered.wait(timeout=5)
            assert client.get("/api/schemas").status_code == 200
            assert upload(client, simple_invoice_pdf_bytes).status_code == 409
            assert client.get("/api/documents").json()["documents"] == []
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 200
        assert len(store.list()) == 1


@pytest.mark.parametrize("schema_name", ["invoice", "receipt", "contract"])
def test_verification_worker_preserves_every_field_and_evidence_coordinate(schema_name):
    from fieldproof.schemas import BUILTIN_SCHEMAS
    from fieldproof.server.pdf_work import verify_server_data
    from fieldproof.verify.engine import verify

    root = Path(__file__).resolve().parents[1]
    document = load_pdf(root / f"examples/{schema_name}.pdf")
    fixture = json.loads((root / f"examples/fixtures/{schema_name}.json").read_text())
    data = BUILTIN_SCHEMAS[schema_name].model_validate(fixture["data"])
    assert (
        verify_server_data(schema_name, data, document).to_dict()
        == verify(data, document).to_dict()
    )


@pytest.mark.skipif(sys.platform != "linux", reason="Linux CPU resource enforcement")
def test_killed_worker_releases_queue_and_next_real_document_loads(
    simple_invoice_pdf_bytes,
    monkeypatch,
):
    from fieldproof.server import pdf_work

    original = pdf_work.subprocess.run

    def terminated(command, **kwargs):
        script = "import resource; resource.setrlimit(resource.RLIMIT_CPU,(1,1))\nwhile True: pass"
        return original([sys.executable, "-c", script], **kwargs)

    monkeypatch.setattr(pdf_work.subprocess, "run", terminated)
    with pytest.raises(DocumentLimitError, match="resource budget"):
        load_server_pdf(simple_invoice_pdf_bytes, "invoice.pdf")
    monkeypatch.setattr(pdf_work.subprocess, "run", original)
    assert load_server_pdf(simple_invoice_pdf_bytes, "invoice.pdf").page_count == 1
