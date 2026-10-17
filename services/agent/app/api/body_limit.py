"""Reject oversized document uploads before the multipart parser spools them to disk: a
Content-Length check, and a byte count on the stream for chunked bodies (413 either way)."""

import re
from collections.abc import MutableMapping
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.errors import problem

UPLOAD_PATH = re.compile(r"^/deals/[^/]+/documents/?$")
SLACK = 64 * 1024  # multipart framing around the file


class UploadBodyLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not UPLOAD_PATH.match(scope["path"])
        ):
            await self.app(scope, receive, send)
            return
        limit = get_settings().document_max_bytes + SLACK
        headers: MutableMapping[bytes, Any] = dict(scope["headers"])
        declared = headers.get(b"content-length")

        async def reject() -> None:
            resp = problem(
                413,
                "Payload too large",
                f"file is larger than {get_settings().document_max_bytes // (1024 * 1024)} MB",
                "FILE_TOO_LARGE",
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
