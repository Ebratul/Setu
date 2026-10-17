"""Domain exceptions mapped to RFC 7807 problem JSON by one handler. No stack traces or secrets."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError


class DomainError(Exception):
    status = 400
    title = "Bad request"

    def __init__(self, detail: str, code: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code


class Unauthorized(DomainError):
    status = 401
    title = "Not signed in"


class Forbidden(DomainError):
    status = 403
    title = "Forbidden"


class NotFound(DomainError):
    status = 404
    title = "Not found"


class Conflict(DomainError):
    status = 409
    title = "Conflict"


class ServiceUnavailable(DomainError):
    status = 503
    title = "Service unavailable"


def problem(status: int, title: str, detail: str, code: str | None = None) -> JSONResponse:
    body: dict[str, str | int] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
    }
    if code:
        body["code"] = code  # stable machine-readable reason, e.g. EVIDENCE_NOT_VERIFIED
    return JSONResponse(
        body,
        status_code=status,
        media_type="application/problem+json",
    )


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return problem(exc.status, exc.title, exc.detail, exc.code)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, __: Exception) -> JSONResponse:
        return problem(500, "Internal error", "unexpected error")

    @app.exception_handler(OperationalError)
    async def _db_down(_: Request, __: OperationalError) -> JSONResponse:
        return problem(503, "Service unavailable", "database is unavailable")
