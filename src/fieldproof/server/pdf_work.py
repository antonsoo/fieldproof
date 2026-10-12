"""Run PDF parsers outside the API process with bounded work and output."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import BaseModel

from fieldproof.document.limits import DocumentLimitError
from fieldproof.document.loader import EmptyDocumentError
from fieldproof.document.model import Document, OcrProvenance, document_from_dict
from fieldproof.verify.columns import ColumnEvidenceCheck
from fieldproof.verify.cross_field import CrossFieldCheck, CrossFieldIssue
from fieldproof.verify.engine import FieldStatus, FieldVerification, VerificationReport
from fieldproof.verify.rows import RowEvidenceCheck

PDF_TIMEOUT_SECONDS = 30
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
_worker_lock = threading.Lock()
_worker_slots = threading.BoundedSemaphore(4)


class PdfWorkerBusyError(RuntimeError):
    """Reject excess queued work rather than retaining an unbounded backlog."""


def _run_pdf_worker(pdf_bytes: bytes, action: str, argument: str) -> bytes:
    # PDFium is not thread safe. Serializing disposable processes also bounds
    # simultaneous parsing/rendering memory, including requests from other tabs.
    if not _worker_slots.acquire(blocking=False):
        raise PdfWorkerBusyError("PDF processing is busy. Wait, then retry.")
    acquired = False
    try:
        acquired = _worker_lock.acquire(timeout=PDF_TIMEOUT_SECONDS)
        if not acquired:
            raise PdfWorkerBusyError("PDF processing is busy. Wait, then retry.")
        return _execute_pdf_worker(pdf_bytes, action, argument)
    finally:
        if acquired:
            _worker_lock.release()
        _worker_slots.release()


def _execute_pdf_worker(pdf_bytes: bytes, action: str, argument: str) -> bytes:
    with TemporaryDirectory(prefix="fieldproof-pdf-") as directory:
        source = Path(directory) / "input.pdf"
        destination = Path(directory) / "output"
        source.write_bytes(pdf_bytes)
        with (Path(directory) / "error").open("w+b") as errors:
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "fieldproof.document.worker",
                        action,
                        str(source),
                        str(destination),
                        argument,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=errors,
                    timeout=PDF_TIMEOUT_SECONDS,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise DocumentLimitError(
                    f"PDF processing exceeded the {PDF_TIMEOUT_SECONDS}-second time limit"
                ) from exc
            if result.returncode != 0:
                errors.seek(0)
                message = errors.read(1024).decode("utf-8", errors="replace").strip()
                if result.returncode == 2:
                    raise EmptyDocumentError(message)
                if result.returncode == 3:
                    raise DocumentLimitError(message)
                if result.returncode < 0:
                    raise DocumentLimitError("PDF worker exceeded its resource budget")
                raise ValueError(message or "could not process PDF")
        if not destination.is_file() or destination.stat().st_size > MAX_OUTPUT_BYTES:
            raise DocumentLimitError("PDF worker output exceeded its size limit")
        return destination.read_bytes()


def load_server_pdf(pdf_bytes: bytes, filename: str) -> Document:
    raw = json.loads(_run_pdf_worker(pdf_bytes, "load", filename))
    return document_from_dict(raw)


def render_server_page(pdf_bytes: bytes, page_number: int) -> bytes:
    return _run_pdf_worker(pdf_bytes, "render", str(page_number))


def verify_server_data(schema_name: str, data: BaseModel, document: Document) -> VerificationReport:
    content = json.dumps(
        {"document": asdict(document), "data": data.model_dump(mode="json")}
    ).encode()
    if len(content) > MAX_OUTPUT_BYTES:
        raise DocumentLimitError("Verification input exceeded the worker size limit")
    raw = json.loads(_run_pdf_worker(content, "verify", schema_name))
    return VerificationReport(
        fields=[
            FieldVerification(**{**field, "status": FieldStatus(field["status"])})
            for field in raw["fields"]
        ],
        cross_field_issues=[
            CrossFieldIssue(tuple(issue["fields"]), issue["message"])
            for issue in raw["cross_field_issues"]
        ],
        cross_field_checks=[
            CrossFieldCheck(**{**check, "fields": tuple(check["fields"])})
            for check in raw["cross_field_checks"]
        ],
        row_checks=[RowEvidenceCheck(**check) for check in raw["row_checks"]],
        column_checks=[ColumnEvidenceCheck(**check) for check in raw["column_checks"]],
        ocr=OcrProvenance(**raw["ocr"]) if raw.get("ocr") is not None else None,
    )
