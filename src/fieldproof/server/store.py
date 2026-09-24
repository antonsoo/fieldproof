"""In-process document store for the review server.

This is deliberately not a database: fieldproof's server is a local review
tool (`fieldproof serve`), not a multi-user service, and every session's
state - the uploaded PDF, extraction, and review decisions - lives only as
long as the process does. Restarting the server starts over. If you need
persistence across restarts, export the approved values (`/export.json`)
before stopping it.
"""

from __future__ import annotations

import uuid
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


class DocumentStore:
    def __init__(self) -> None:
        self._sessions: dict[str, DocumentSession] = {}

    def create(self, filename: str, pdf_bytes: bytes, document: Document) -> DocumentSession:
        session_id = uuid.uuid4().hex
        session = DocumentSession(
            id=session_id, filename=filename, pdf_bytes=pdf_bytes, document=document
        )
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> DocumentSession | None:
        return self._sessions.get(session_id)


#: Module-level singleton - the server process has exactly one store.
store = DocumentStore()
