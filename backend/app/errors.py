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


class PayloadTooLarge(DomainError):
    status = 413
    title = "Payload too large"


class UnsupportedMedia(DomainError):
    status = 415
    title = "Unsupported media type"


class Gone(DomainError):
    status = 410
    title = "Gone"


class TooManyRequests(DomainError):
    status = 429
    title = "Too many requests"


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
    from app.db.tenancy import SchemaMissing

    @app.exception_handler(SchemaMissing)
    async def _gone(_: Request, __: SchemaMissing) -> JSONResponse:
        return problem(
            410, "Gone", "this sandbox is being rebuilt or has expired; reload", "SANDBOX_EXPIRED"
        )

    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return problem(exc.status, exc.title, exc.detail, exc.code)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, __: Exception) -> JSONResponse:
        return problem(500, "Internal error", "unexpected error")

    @app.exception_handler(OperationalError)
    async def _db_down(_: Request, __: OperationalError) -> JSONResponse:
        return problem(503, "Service unavailable", "database is unavailable")
