"""Reject oversized request bodies before they are parsed: a Content-Length check, and a byte
count on the stream for chunked bodies (413 either way). Document uploads get their own limit
(DOCUMENT_MAX_BYTES, kept <= 4 MB for Vercel's 4.5 MB function cap, before the multipart parser
spools to disk); every other body, JSON included, is capped at MAX_BODY_BYTES (default 1 MB)."""

import re
from collections.abc import MutableMapping
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.errors import problem

UPLOAD_PATH = re.compile(r"^(/deals/[^/]+/documents|/registry/lender-check/file)/?$")
SLACK = 64 * 1024  # multipart framing around the file


class BodyLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH", "DELETE"):
            await self.app(scope, receive, send)
            return
        settings = get_settings()
        is_upload = scope["method"] == "POST" and UPLOAD_PATH.match(scope["path"]) is not None
        limit = settings.document_max_bytes + SLACK if is_upload else settings.max_body_bytes
        headers: MutableMapping[bytes, Any] = dict(scope["headers"])
        declared = headers.get(b"content-length")

        async def reject() -> None:
            if is_upload:
                resp = problem(
                    413,
                    "Payload too large",
                    f"file is larger than {settings.document_max_bytes // (1024 * 1024)} MB",
                    "FILE_TOO_LARGE",
                )
            else:
                resp = problem(
                    413,
                    "Payload too large",
                    f"request body is larger than {settings.max_body_bytes // 1024} KB",
                    "BODY_TOO_LARGE",
                )
            await resp(scope, receive, send)

        if declared is not None and declared.isdigit() and int(declared) > limit:
            await reject()
            return
        seen = 0
        exceeded = False

        async def counting() -> Message:
            nonlocal seen, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > limit:  # stop feeding the parser; answer 413 once it has given up
                    exceeded = True
                    return {"type": "http.disconnect"}
            return msg

        async def tracking(message: Message) -> None:
            if not exceeded:  # whatever the app says after we cut the body off is dropped
                await send(message)

        try:
            await self.app(scope, counting, tracking)
        except Exception:
            if not exceeded:
                raise
        if exceeded:
            await reject()
