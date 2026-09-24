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
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from fieldproof.document.loader import EmptyDocumentError, load_pdf
from fieldproof.document.render import render_page_png
from fieldproof.extract.anthropic_provider import AnthropicExtractor
from fieldproof.extract.base import ExtractionResult
from fieldproof.schemas import BUILTIN_SCHEMAS
from fieldproof.server.store import DocumentSession, ReviewState, store
from fieldproof.verify.engine import verify

app = FastAPI(title="fieldproof", version="0.1.0")


def _find_static_dir() -> Path:
    """The built web UI, if present - not committed (it's build output), so
    a fresh clone has neither candidate until `npm run build` is run in
    web/. Checked in order: an explicit override, a copy already placed
    next to this file (e.g. by packaging), and web/dist relative to the
    repo checkout (the normal case for `pip install -e .` + `fieldproof
    serve` from source)."""
    if override := os.environ.get("FIELDPROOF_STATIC_DIR"):
        return Path(override)
    bundled = Path(__file__).parent / "static"
    if (bundled / "index.html").exists():
        return bundled
    repo_dist = Path(__file__).resolve().parents[3] / "web" / "dist"
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
async def upload_document(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
    pdf_bytes = await file.read()
    try:
        document = load_pdf(pdf_bytes, label=file.filename or "document.pdf")
    except EmptyDocumentError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{exc} (scanned/image-only PDFs need the optional OCR extra - see README)",
        ) from exc
    except Exception as exc:  # pdfplumber raises a variety of parse errors
        raise HTTPException(status_code=422, detail=f"could not read PDF: {exc}") from exc

    session = store.create(
        filename=file.filename or "document.pdf", pdf_bytes=pdf_bytes, document=document
    )
    return _document_summary(session)


def _document_summary(session: DocumentSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "filename": session.filename,
        "page_count": session.document.page_count,
        "pages": [
            {"number": p.number, "width": p.width, "height": p.height}
            for p in session.document.pages
        ],
    }


@app.get("/api/documents/{document_id}")
def get_document(document_id: str) -> dict[str, Any]:
    return _document_summary(_session_or_404(document_id))


@app.get("/api/documents/{document_id}/pages/{page_number}.png")
def get_page_image(document_id: str, page_number: int) -> Response:
    session = _session_or_404(document_id)
    if not 1 <= page_number <= session.document.page_count:
        raise HTTPException(status_code=404, detail=f"no page {page_number}")
    png_bytes = render_page_png(session.pdf_bytes, page_number)
    return Response(content=png_bytes, media_type="image/png")


@app.post("/api/documents/{document_id}/extract")
async def extract_document(
    document_id: str,
    schema_name: Annotated[str, Form(alias="schema")],
    provider: Annotated[str, Form()] = "fixture",
    fixture: Annotated[UploadFile | None, File()] = None,
) -> dict[str, Any]:
    session = _session_or_404(document_id)
    schema = BUILTIN_SCHEMAS.get(schema_name)
    if schema is None:
        raise HTTPException(
            status_code=400,
            detail=f"unknown schema {schema_name!r} - choose one of {sorted(BUILTIN_SCHEMAS)}",
        )

    if provider == "fixture":
        if fixture is None:
            raise HTTPException(status_code=400, detail="provider=fixture requires a fixture file")
        raw = json.loads((await fixture.read()).decode("utf-8"))
        payload = raw.get("data", raw)
        data = schema.model_validate(payload)
        extraction = ExtractionResult(
            schema_name=schema.__name__, data=data, provider="fixture", model=raw.get("model")
        )
    elif provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise HTTPException(
                status_code=400,
                detail="provider=anthropic requires ANTHROPIC_API_KEY to be set on the server",
            )
        extraction = AnthropicExtractor().extract(session.document, schema)
    else:
        raise HTTPException(status_code=400, detail=f"unknown provider {provider!r}")

    report = verify(extraction.data, session.document)

    session.schema_name = schema_name
    session.extraction = extraction
    session.report = report
    session.review = {f.path: ReviewState() for f in report.fields}

    return _result_payload(session)


def _result_payload(session: DocumentSession) -> dict[str, Any]:
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
    if session.report is None:
        raise HTTPException(status_code=404, detail="no extraction has been run yet")
    if req.path not in session.review:
        raise HTTPException(status_code=404, detail=f"no field {req.path!r}")

    if req.action == "approve":
        session.review[req.path] = ReviewState(status="approved")
    elif req.action == "edit":
        session.review[req.path] = ReviewState(status="edited", edited_value=req.value)
    elif req.action == "reject":
        session.review[req.path] = ReviewState(status="rejected")
    elif req.action == "reset":
        session.review[req.path] = ReviewState(status="pending")
    else:
        raise HTTPException(status_code=400, detail=f"unknown action {req.action!r}")

    state = session.review[req.path]
    return {"path": req.path, "status": state.status, "edited_value": state.edited_value}


def _exported_rows(session: DocumentSession) -> list[dict[str, Any]]:
    assert session.report is not None
    rows = []
    for f in session.report.fields:
        review = session.review.get(f.path, ReviewState())
        if review.status == "rejected":
            continue
        value = review.edited_value if review.status == "edited" else f.value
        rows.append(
            {
                "field": f.path,
                "value": value,
                "verification_status": f.status.value,
                "review_status": review.status,
                "page": f.page,
            }
        )
    return rows


@app.get("/api/documents/{document_id}/export.json")
def export_json(document_id: str) -> JSONResponse:
    session = _session_or_404(document_id)
    if session.report is None:
        raise HTTPException(status_code=404, detail="no extraction has been run yet")
    return JSONResponse(content=_exported_rows(session))


@app.get("/api/documents/{document_id}/export.csv")
def export_csv(document_id: str) -> PlainTextResponse:
    session = _session_or_404(document_id)
    if session.report is None:
        raise HTTPException(status_code=404, detail="no extraction has been run yet")
    rows = _exported_rows(session)
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=["field", "value", "verification_status", "review_status", "page"]
    )
    writer.writeheader()
    writer.writerows(rows)
    return PlainTextResponse(content=buf.getvalue(), media_type="text/csv")


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
