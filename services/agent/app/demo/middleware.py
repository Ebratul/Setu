"""Pure-ASGI middleware: route a request to the judge's sandbox schema. The signed `setu_sandbox`
cookie names the sandbox; its schema becomes the request's `search_path` (app/db/tenancy.py) and
the sandbox is visible to the LLM layer. A cookie that no longer resolves gets 410 (the page then
offers a fresh sandbox) instead of silently falling back to the shared demo data. Per-sandbox
rate limits apply here too."""

from starlette.requests import cookie_parser
from starlette.types import ASGIApp, Receive, Scope, Send

from app.demo import sandbox
from app.demo.context import use_sandbox
from app.errors import problem

OPEN = ("/health", "/docs", "/openapi.json", "/redoc")


class SandboxMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        raw = dict(scope["headers"]).get(b"cookie", b"").decode("latin-1")
        if sandbox.COOKIE_NAME not in raw:
            await self.app(scope, receive, send)
            return
        # A tolerant parser: one odd cookie from another tool must not hide ours (that would
        # fall through to the shared data). The cookie name is present, so it must resolve.
        value = cookie_parser(raw).get(sandbox.COOKIE_NAME, "")

        path, method = scope["path"], scope["method"]
        if path.startswith(OPEN) or (path == "/demo/sandbox" and method in ("POST", "DELETE")):
            await self.app(scope, receive, send)
            return
        sandbox_id = sandbox.parse_token(value)
        info = sandbox.lookup(sandbox_id) if sandbox_id else None
        if info is None:
            response = problem(
                410,
                "Gone",
                "this sandbox has expired or does not exist; start a new one",
                "SANDBOX_EXPIRED",
            )
            await response(scope, receive, send)
            return
        wait = sandbox.allow(info.id, method, path)
        if wait is not None:
            response = problem(
                429,
                "Too many requests",
                "this sandbox is going too fast; slow down a little",
                "SANDBOX_RATE_LIMIT",
            )
            response.headers["Retry-After"] = str(int(wait) + 1)
            await response(scope, receive, send)
            return
        with use_sandbox(info):
            await self.app(scope, receive, send)
