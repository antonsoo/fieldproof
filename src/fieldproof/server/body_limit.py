"""Reject oversized bodies while streaming, before multipart spooling completes."""

from __future__ import annotations

import threading

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_FIXTURE_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 30 * 1024 * 1024


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._slots = threading.BoundedSemaphore(4)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or scope.get("method") != "POST" or not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return
        maximum = (
            MAX_ARCHIVE_BYTES + 1024 * 1024
            if path == "/api/archives"
            else MAX_PDF_BYTES + 1024 * 1024
            if path == "/api/documents"
            else MAX_FIXTURE_BYTES + 1024 * 1024
            if path.endswith("/extract")
            else 64 * 1024
        )
        detail = (
            f"Request exceeds the {maximum // 1024:,} KiB limit. Choose a smaller file or value."
        )
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    too_large = int(value) > maximum
                except ValueError:
                    too_large = True
                if too_large:
                    await JSONResponse({"detail": detail}, status_code=413)(scope, receive, send)
                    return
        consumed = 0

        async def limited_receive() -> Message:
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > maximum:
                    # FastAPI propagates this from request parsing; Starlette's
                    # multipart parser closes partial spooled files on failure.
                    raise HTTPException(status_code=413, detail=detail)
            return message

        if not self._slots.acquire(blocking=False):
            await JSONResponse(
                {"detail": "Server intake is busy. Wait, then retry."},
                status_code=503,
            )(scope, receive, send)
            return
        try:
            await self.app(scope, limited_receive, send)
        finally:
            self._slots.release()
