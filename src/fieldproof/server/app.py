"""FastAPI app: upload a document, run extraction, serve the review UI and
results, export approved values.

Run with `fieldproof serve` (see `fieldproof.cli`), or directly with
`uvicorn fieldproof.server.app:app`.
"""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from fieldproof import __version__
from fieldproof.document.limits import DocumentLimitError, DocumentLimits
from fieldproof.document.loader import EmptyDocumentError
from fieldproof.extract.anthropic_provider import AnthropicExtractor
from fieldproof.extract.base import (
    ExtractionError,
    ExtractionResult,
    read_extraction_json,
    validate_data,
)
from fieldproof.schemas import BUILTIN_SCHEMAS, iter_evidenced_fields
from fieldproof.server.archive import decode_archive, encode_archive, valid_correction
from fieldproof.server.body_limit import (
    MAX_ARCHIVE_BYTES,
    MAX_FIXTURE_BYTES,
    MAX_PDF_BYTES,
    BodyLimitMiddleware,
)
from fieldproof.server.pdf_work import (
    PdfWorkerBusyError,
    load_server_pdf,
    render_server_page,
    verify_server_data,
)
from fieldproof.server.spreadsheet import XLSX_MIME, rows_to_xlsx
from fieldproof.server.store import (
    DocumentSession,
    ReviewState,
    SessionBusyError,
    StoreCapacityError,
    store,
)

app = FastAPI(title="fieldproof", version=__version__)
app.add_middleware(BodyLimitMiddleware)


def _find_static_dir() -> Path:
    """The built web UI, if present - not committed (it's build output), so
    a fresh clone has neither candidate until `npm run build` is run in
    web/. An explicit override wins. In a source checkout, prefer the
    source build to a potentially stale packaged copy. Installed wheels
    use the copy next to this file."""
    if override := os.environ.get("FIELDPROOF_STATIC_DIR"):
        return Path(override)
    bundled = Path(__file__).parent / "static"
    source_root = Path(__file__).resolve().parents[3]
    repo_dist = source_root / "web" / "dist"
    if (source_root / "pyproject.toml").is_file() and (repo_dist / "index.html").is_file():
        return repo_dist
    if (bundled / "index.html").exists():
        return bundled
    return repo_dist


#: When absent, "/" returns a short message instead of a 404, so a fresh
#: `git clone` isn't confusing to run before the UI has been built.
_STATIC_DIR = _find_static_dir()


def _session_or_404(document_id: str) -> DocumentSession:
    session = store.get(document_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"no document with id {document_id!r}")
    return session


@app.get("/api/schemas")
def list_schemas() -> dict[str, list[str]]:
    return {"schemas": sorted(BUILTIN_SCHEMAS)}


@app.post("/api/documents")
async def upload_document(request: Request, file: Annotated[UploadFile, File()]) -> dict[str, Any]:
    if file.size is not None and file.size > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF exceeds the 25 MiB upload limit")
    filename = (file.filename or "document.pdf")[:255]
    try:
        with store.reserve_upload(file.size if file.size is not None else MAX_PDF_BYTES) as token:
            pdf_bytes = await file.read(MAX_PDF_BYTES + 1)
            if len(pdf_bytes) > MAX_PDF_BYTES:
                raise HTTPException(status_code=413, detail="PDF exceeds the 25 MiB upload limit")
            document = await run_in_threadpool(load_server_pdf, pdf_bytes, filename)
            if await request.is_disconnected():
                raise HTTPException(status_code=499, detail="Upload cancelled before storing")
            session = store.create(
                filename=filename,
                pdf_bytes=pdf_bytes,
                document=document,
                reservation=token,
            )
    except StoreCapacityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (SessionBusyError, PdfWorkerBusyError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DocumentLimitError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except EmptyDocumentError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{exc}. Use fieldproof extract with the OCR extra for scanned PDFs.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"could not read PDF: {exc}") from exc
    return _document_summary(session)


@app.post("/api/archives")
async def restore_archive(request: Request, file: Annotated[UploadFile, File()]) -> dict[str, Any]:
    if file.size is not None and file.size > MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="Review archive exceeds the 30 MiB limit")
    try:
        # Reserve a session/worker slot before decoding. The PDF byte budget is
        # checked with its actual size at the atomic create below.
        with store.reserve_upload(0) as token:
            content = await file.read(MAX_ARCHIVE_BYTES + 1)
            archived = await run_in_threadpool(decode_archive, content)
            document = await run_in_threadpool(
                load_server_pdf, archived.pdf_bytes, archived.filename
            )
            report = await run_in_threadpool(
                verify_server_data, archived.schema_name, archived.extraction.data, document
            )
            if await request.is_disconnected():
                raise HTTPException(status_code=499, detail="Restore cancelled before storing")
            session = store.create(
                archived.filename,
                archived.pdf_bytes,
                document,
                reservation=token,
                schema_name=archived.schema_name,
                extraction=archived.extraction,
                report=report,
                review=archived.review,
                restored_from_archive=True,
            )
    except StoreCapacityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (SessionBusyError, PdfWorkerBusyError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DocumentLimitError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Could not restore review: {exc}") from exc
    return {"document": _document_summary(session), "extraction": _result_payload(session)}


@app.get("/api/documents/{document_id}/archive")
def save_archive(document_id: str) -> Response:
    session = _session_or_404(document_id)
    try:
        with session.review_lock:
            if store.get(document_id) is not session:
                raise HTTPException(status_code=404, detail="Document was removed")
            if store.is_busy(document_id):
                raise HTTPException(
                    status_code=409, detail="Extraction is running; save the archive afterwards"
                )
            content = encode_archive(session)
    except DocumentLimitError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(
        content,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="fieldproof-review.zip"',
            "Cache-Control": "no-store",
        },
    )


def _document_summary(session: DocumentSession) -> dict[str, Any]:
    with session.review_lock:
        return {
            "id": session.id,
            "filename": session.filename,
            "pdf_bytes": len(session.pdf_bytes),
            "page_count": session.document.page_count,
            "pages": [
                {"number": p.number, "width": p.width, "height": p.height}
                for p in session.document.pages
            ],
            "has_extraction": session.report is not None,
            "reviewed_count": sum(r.status != "pending" for r in session.review.values()),
            "field_count": len(session.review),
            "busy": store.is_busy(session.id),
            "restored_from_archive": session.restored_from_archive,
        }


@app.get("/api/documents")
def list_documents() -> dict[str, Any]:
    return {
        "documents": [_document_summary(session) for session in store.list()],
        "max_sessions": store.max_sessions,
        "max_pdf_bytes": MAX_PDF_BYTES,
        "max_pages": DocumentLimits().max_pages,
    }


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: str) -> Response:
    try:
        removed = store.delete(document_id)
    except SessionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="Document was already removed")
    return Response(status_code=204)


@app.get("/api/documents/{document_id}")
def get_document(document_id: str) -> dict[str, Any]:
    return _document_summary(_session_or_404(document_id))


@app.get("/api/documents/{document_id}/pages/{page_number}.png")
async def get_page_image(document_id: str, page_number: int) -> Response:
    session = _session_or_404(document_id)
    if not 1 <= page_number <= session.document.page_count:
        raise HTTPException(status_code=404, detail=f"no page {page_number}")
    try:
        png_bytes = await run_in_threadpool(render_server_page, session.pdf_bytes, page_number)
    except PdfWorkerBusyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DocumentLimitError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(content=png_bytes, media_type="image/png")


@app.post("/api/documents/{document_id}/extract")
async def extract_document(
    document_id: str,
    schema_name: Annotated[str, Form(alias="schema")],
    provider: Annotated[str, Form()] = "fixture",
    fixture: Annotated[UploadFile | None, File()] = None,
) -> dict[str, Any]:
    session = _session_or_404(document_id)
    try:
        with store.extracting(session):
            schema = BUILTIN_SCHEMAS.get(schema_name)
            if schema is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"unknown schema {schema_name!r} - choose one of {sorted(BUILTIN_SCHEMAS)}"
                    ),
                )

            if provider == "fixture":
                if fixture is None:
                    raise HTTPException(
                        status_code=400, detail="provider=fixture requires a fixture file"
                    )
                source = fixture.filename or "the uploaded extraction"
                try:
                    if fixture.size is not None and fixture.size > MAX_FIXTURE_BYTES:
                        raise HTTPException(
                            status_code=413, detail="Fixture JSON exceeds the 2 MiB limit"
                        )
                    content = await fixture.read(MAX_FIXTURE_BYTES + 1)
                    if len(content) > MAX_FIXTURE_BYTES:
                        raise HTTPException(
                            status_code=413, detail="Fixture JSON exceeds the 2 MiB limit"
                        )
                    raw = read_extraction_json(content, source)
                    data = validate_data(raw.get("data", raw), schema, source)
                except ExtractionError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                model = raw.get("model")
                extraction = ExtractionResult(
                    schema_name=schema.__name__,
                    data=data,
                    provider="fixture",
                    model=model if isinstance(model, str) else None,
                )
            elif provider == "anthropic":
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "provider=anthropic requires ANTHROPIC_API_KEY to be set on the server"
                        ),
                    )
                try:
                    extraction = await run_in_threadpool(
                        AnthropicExtractor().extract, session.document, schema
                    )
                except ExtractionError as exc:
                    raise HTTPException(status_code=502, detail=str(exc)) from exc
            else:
                raise HTTPException(status_code=400, detail=f"unknown provider {provider!r}")

            for count, _field in enumerate(iter_evidenced_fields(extraction.data), start=1):
                if count > 2_000:
                    raise HTTPException(
                        status_code=413, detail="Extraction exceeds the 2,000-field review limit"
                    )
            report = await run_in_threadpool(
                verify_server_data, schema_name, extraction.data, session.document
            )

            with session.review_lock:
                session.schema_name = schema_name
                session.extraction = extraction
                session.report = report
                session.review = {f.path: ReviewState() for f in report.fields}

            return _result_payload(session)
    except SessionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PdfWorkerBusyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DocumentLimitError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Document was removed") from exc


def _result_payload(session: DocumentSession) -> dict[str, Any]:
    with session.review_lock:
        assert session.extraction is not None and session.report is not None
        return {
            "schema": session.schema_name,
            "provider": session.extraction.provider,
            "model": session.extraction.model,
            "data": session.extraction.data.model_dump(mode="json"),
            "report": session.report.to_dict(),
            "review": {
                path: {"status": r.status, "edited_value": r.edited_value}
                for path, r in session.review.items()
            },
        }


@app.get("/api/documents/{document_id}/report")
def get_report(document_id: str) -> dict[str, Any]:
    session = _session_or_404(document_id)
    if session.report is None:
        raise HTTPException(status_code=404, detail="no extraction has been run yet")
    return _result_payload(session)


class ReviewRequest(BaseModel):
    path: str
    action: str  # approve | edit | reject | reset
    value: Any = None


@app.post("/api/documents/{document_id}/review")
def review_field(document_id: str, req: ReviewRequest) -> dict[str, Any]:
    session = _session_or_404(document_id)
    with session.review_lock:
        if store.get(document_id) is not session:
            raise HTTPException(status_code=404, detail="Document was removed")
        if store.is_busy(document_id):
            raise HTTPException(
                status_code=409, detail="Extraction is running; retry this decision afterwards"
            )
        if session.report is None:
            raise HTTPException(status_code=404, detail="no extraction has been run yet")
        if req.path not in session.review:
            raise HTTPException(status_code=404, detail=f"no field {req.path!r}")

        if req.action == "approve":
            session.review[req.path] = ReviewState(
                status="approved", edited_value=session.review[req.path].edited_value
            )
        elif req.action == "edit":
            original = next(f.value for f in session.report.fields if f.path == req.path)
            if not valid_correction(original, req.value):
                raise HTTPException(
                    status_code=422,
                    detail="correction must keep the field's scalar type and be finite",
                )
            if isinstance(req.value, str):
                try:
                    req.value.encode("utf-8")
                except UnicodeEncodeError as exc:
                    raise HTTPException(
                        status_code=422, detail="Correction must contain valid Unicode"
                    ) from exc
            correction_bytes = len(json.dumps(req.value, ensure_ascii=False).encode("utf-8"))
            correction_bytes += sum(
                len(json.dumps(entry.edited_value, ensure_ascii=False).encode("utf-8"))
                for path, entry in session.review.items()
                if path != req.path and entry.edited_value is not None
            )
            if correction_bytes > 1024 * 1024:
                raise HTTPException(
                    status_code=413,
                    detail="Corrections exceed the 1 MiB limit; export and start a new review",
                )
            session.review[req.path] = ReviewState(status="edited", edited_value=req.value)
        elif req.action == "reject":
            session.review[req.path] = ReviewState(
                status="rejected", edited_value=session.review[req.path].edited_value
            )
        elif req.action == "reset":
            session.review[req.path] = ReviewState(status="pending")
        else:
            raise HTTPException(status_code=400, detail=f"unknown action {req.action!r}")

        state = session.review[req.path]
        return {"path": req.path, "status": state.status, "edited_value": state.edited_value}


def _exported_rows(
    session: DocumentSession, scope: Literal["all", "reviewed"] = "all"
) -> list[dict[str, Any]]:
    with session.review_lock:
        assert session.report is not None
        rows = []
        for f in session.report.fields:
            review = session.review.get(f.path, ReviewState())
            if review.status == "rejected":
                continue
            if scope == "reviewed" and review.status not in {"approved", "edited"}:
                continue
            value = review.edited_value if review.edited_value is not None else f.value
            rows.append(
                {
                    "field": f.path,
                    "value": value,
                    "original_value": f.value,
                    "value_source": "correction"
                    if review.edited_value is not None
                    else "extraction",
                    "verification_status": f.status.value,
                    "review_status": review.status,
                    "page": f.page,
                }
            )
        return rows


@app.get("/api/documents/{document_id}/export.json")
def export_json(document_id: str, scope: Literal["all", "reviewed"] = "all") -> JSONResponse:
    session = _session_or_404(document_id)
    if session.report is None:
        raise HTTPException(status_code=404, detail="no extraction has been run yet")
    return JSONResponse(content=_exported_rows(session, scope))


@app.get("/api/documents/{document_id}/export.csv")
def export_csv(document_id: str, scope: Literal["all", "reviewed"] = "all") -> PlainTextResponse:
    session = _session_or_404(document_id)
    if session.report is None:
        raise HTTPException(status_code=404, detail="no extraction has been run yet")
    rows = _exported_rows(session, scope)
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=[
            "field",
            "value",
            "original_value",
            "value_source",
            "verification_status",
            "review_status",
            "page",
        ],
    )
    writer.writeheader()
    writer.writerows(
        {
            key: str(value).lower() if isinstance(value, bool) else value
            for key, value in row.items()
        }
        for row in rows
    )
    return PlainTextResponse(content=buf.getvalue(), media_type="text/csv")


@app.get("/api/documents/{document_id}/export.xlsx")
def export_xlsx(document_id: str, scope: Literal["all", "reviewed"] = "all") -> Response:
    session = _session_or_404(document_id)
    if session.report is None:
        raise HTTPException(status_code=404, detail="no extraction has been run yet")
    try:
        workbook = rows_to_xlsx(_exported_rows(session, scope))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=workbook,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": 'attachment; filename="fieldproof.xlsx"'},
    )


if _STATIC_DIR.is_dir() and (_STATIC_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
else:

    @app.get("/")
    def no_ui() -> dict[str, str]:
        return {
            "message": (
                "fieldproof API is running, but the review UI hasn't been built. "
                "Run `npm ci && npm run build` in web/, or use the API directly - see /docs."
            )
        }
