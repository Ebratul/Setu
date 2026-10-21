"""Route class that turns FastAPI request-validation failures into one friendly problem+json:

    {"status": 422, "code": "VALIDATION_FAILED", "errors": [{"field": "address.district",
     "code": "required", "message": "..."}]}

Used by the onboarding router so the wizard can map each error to its input. A request body that
is a union of models (buyer vs supplier business) keeps only the errors of the branch that fits
best (the fewest errors). The submitted values are never echoed back."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.errors import problem

_CODES = {
    "missing": "required",
    "string_too_short": "too_short",
    "string_too_long": "too_long",
    "string_pattern_mismatch": "invalid_format",
    "extra_forbidden": "not_allowed",
    "literal_error": "invalid_choice",
    "date_parsing": "invalid_date",
    "date_from_datetime_parsing": "invalid_date",
    "json_invalid": "invalid_json",
    "int_parsing": "invalid_number",
    "greater_than_equal": "too_small",
    "less_than_equal": "too_large",
    "enum": "invalid_choice",
}


def _branch(loc: tuple[Any, ...]) -> str | None:
    # body.<ModelName>.<field...> for union members
    return str(loc[1]) if len(loc) > 2 and str(loc[1]).endswith("In") else None


def friendly_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    raw = [e for e in exc.errors() if e.get("loc")]
    branches: dict[str, list[dict[str, Any]]] = {}
    plain: list[dict[str, Any]] = []
    for e in raw:
        b = _branch(tuple(e["loc"]))
        if b is None:
            plain.append(e)
        else:
            branches.setdefault(b, []).append(e)
    if branches:
        plain.extend(min(branches.values(), key=len))
    out: list[dict[str, str]] = []
    for e in plain:
        loc = [str(p) for p in e["loc"] if p != "body"]
        if loc and loc[0].endswith("In") and len(loc) > 1:
            loc = loc[1:]
        kind = str(e.get("type", "invalid"))
        out.append(
            {
                "field": ".".join(loc) or "body",
                "code": _CODES.get(kind, kind.upper() if kind.isupper() else kind),
                "message": str(e.get("msg", "invalid value"))[:200],
            }
        )
    return out[:50]


class FriendlyRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as exc:
                return problem(
                    422,
                    "Validation failed",
                    "some fields need attention",
                    "VALIDATION_FAILED",
                    friendly_errors(exc),
                )

        return handler
