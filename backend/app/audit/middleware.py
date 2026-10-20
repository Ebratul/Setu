"""Pure-ASGI middleware: put the signed-in user's id in a context variable so `write_audit`
records who acted without every call site passing it. Context set here is visible to the
threadpool workers FastAPI runs sync endpoints in."""

from http.cookies import SimpleCookie

from starlette.types import ASGIApp, Receive, Scope, Send

from app.audit.writer import current_actor_id


class AuditActorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        from app.auth.demo import COOKIE_NAME, parse_token
        from app.config import get_settings

        if get_settings().auth_mode != "demo":  # bind_actor sets the actor from the bearer
            await self.app(scope, receive, send)
            return
        raw = dict(scope["headers"]).get(b"cookie", b"").decode("latin-1")
        cookie: SimpleCookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:
            cookie = SimpleCookie()
        morsel = cookie.get(COOKIE_NAME)
        uid = parse_token(morsel.value) if morsel else None
        reset = current_actor_id.set(str(uid) if uid else None)
        try:
            await self.app(scope, receive, send)
        finally:
            current_actor_id.reset(reset)
