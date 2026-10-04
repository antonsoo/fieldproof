"""In-process document store for the review server.

This is deliberately not a database: fieldproof's server is a local review
tool (`fieldproof serve`), not a multi-user service, and every session's
state - the uploaded PDF, extraction, and review decisions - lives only as
long as the process does. Restarting the server starts over. If you need
persistence across restarts, export the approved values (`/export.json`)
before stopping it.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from fieldproof.document.model import Document
from fieldproof.extract.base import ExtractionResult
from fieldproof.verify.engine import VerificationReport


@dataclass
class ReviewState:
    status: str = "pending"  # pending | approved | edited | rejected
    edited_value: Any = None


@dataclass
class DocumentSession:
    id: str
    filename: str
    pdf_bytes: bytes
    document: Document
    schema_name: str | None = None
    extraction: ExtractionResult | None = None
    report: VerificationReport | None = None
    review: dict[str, ReviewState] = field(default_factory=dict)
    review_lock: Any = field(default_factory=threading.RLock, repr=False, compare=False)


class StoreCapacityError(ValueError):
    """New work is refused without evicting an existing document."""


class SessionBusyError(ValueError):
    """An extraction owns this session until it finishes."""


class DocumentStore:
    def __init__(
        self,
        *,
        max_sessions: int = 8,
        max_pdf_bytes: int = 100 * 1024 * 1024,
        max_words: int = 200_000,
        max_pending_uploads: int = 2,
    ) -> None:
        self._sessions: dict[str, DocumentSession] = {}
        self._reservations: dict[str, int] = {}
        self._busy: set[str] = set()
        self._lock = threading.RLock()
        self.max_sessions = max_sessions
        self.max_pdf_bytes = max_pdf_bytes
        self.max_words = max_words
        self.max_pending_uploads = max_pending_uploads

    def _check_capacity(self, pdf_size: int, *, reservation: str | None = None) -> None:
        reserved = {key: size for key, size in self._reservations.items() if key != reservation}
        if len(self._sessions) + len(reserved) >= self.max_sessions:
            raise StoreCapacityError(
                f"All {self.max_sessions} document slots are in use. "
                "Open Sessions to export and remove a document before uploading another."
            )
        used = sum(len(session.pdf_bytes) for session in self._sessions.values())
        if used + sum(reserved.values()) + pdf_size > self.max_pdf_bytes:
            raise StoreCapacityError(
                f"Stored PDFs reached the {self.max_pdf_bytes / (1024 * 1024):g} MiB capacity. "
                "Open Sessions to export and remove a document before uploading another."
            )

    @contextmanager
    def reserve_upload(self, pdf_size: int) -> Iterator[str]:
        with self._lock:
            if len(self._reservations) >= self.max_pending_uploads:
                raise SessionBusyError("PDF loading is busy. Wait for it to finish, then retry.")
            self._check_capacity(pdf_size)
            token = uuid.uuid4().hex
            self._reservations[token] = pdf_size
        try:
            yield token
        finally:
            with self._lock:
                self._reservations.pop(token, None)

    def create(
        self,
        filename: str,
        pdf_bytes: bytes,
        document: Document,
        *,
        reservation: str | None = None,
    ) -> DocumentSession:
        with self._lock:
            self._check_capacity(len(pdf_bytes), reservation=reservation)
            words = sum(len(page.words) for page in document.pages)
            used_words = sum(
                len(page.words)
                for session in self._sessions.values()
                for page in session.document.pages
            )
            if used_words + words > self.max_words:
                raise StoreCapacityError(
                    "Stored text has reached the server's capacity. "
                    "Open Sessions to export and remove a document before uploading another."
                )
            session = DocumentSession(
                id=uuid.uuid4().hex, filename=filename, pdf_bytes=pdf_bytes, document=document
            )
            self._sessions[session.id] = session
            if reservation is not None:
                self._reservations.pop(reservation, None)
            return session

    def get(self, session_id: str) -> DocumentSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list(self) -> list[DocumentSession]:
        with self._lock:
            return list(self._sessions.values())

    def delete(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            return False
        with session.review_lock, self._lock:
            if self._sessions.get(session_id) is not session:
                return False
            if session_id in self._busy:
                raise SessionBusyError(
                    "Extraction is still running. Wait before removing this session."
                )
            return self._sessions.pop(session_id, None) is not None

    def is_busy(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._busy

    @contextmanager
    def extracting(self, session: DocumentSession) -> Iterator[None]:
        with self._lock:
            if self._sessions.get(session.id) is not session:
                raise KeyError(session.id)
            if session.id in self._busy:
                raise SessionBusyError("Extraction is already running for this document.")
            self._busy.add(session.id)
        try:
            yield
        finally:
            with self._lock:
                self._busy.discard(session.id)


#: Module-level singleton - the server process has exactly one store.
store = DocumentStore()
