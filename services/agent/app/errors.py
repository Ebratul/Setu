"""Domain exceptions mapped to RFC 7807 problem JSON by one handler. No stack traces or secrets."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError


class DomainError(Exception):
    status = 400
    title = "Bad request"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class Unauthorized(DomainError):
    status = 401
    title = "Not signed in"


class Forbidden(DomainError):
    status = 403
    title = "Forbidden"


class NotFound(DomainError):
    status = 404
    title = "Not found"


class ServiceUnavailable(DomainError):
    status = 503
    title = "Service unavailable"


def problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        {"type": "about:blank", "title": title, "status": status, "detail": detail},
        status_code=status,
        media_type="application/problem+json",
    )


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return problem(exc.status, exc.title, exc.detail)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, __: Exception) -> JSONResponse:
        return problem(500, "Internal error", "unexpected error")

    @app.exception_handler(OperationalError)
    async def _db_down(_: Request, __: OperationalError) -> JSONResponse:
        return problem(503, "Service unavailable", "database is unavailable")
