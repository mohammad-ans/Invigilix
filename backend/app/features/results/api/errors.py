"""Uniform error handling and Cache-Control enforcement for the results router."""
from __future__ import annotations

from typing import Any, Callable, Coroutine

from fastapi import HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from ..domain import Conflict, Forbidden, Issue, NotFound, ResultsError, ValidationFailed

STATUS_BY_ERROR: dict[type[ResultsError], int] = {
    ValidationFailed: 422,
    Forbidden: 403,
    NotFound: 404,
    Conflict: 409,
}


def error_body(code: str, message: str, issues: tuple[Issue, ...] | list[Issue] = ()) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "issues": [
                {
                    k: v
                    for k, v in {
                        "code": issue.code,
                        "message": issue.message,
                        "field": issue.field,
                        "item": issue.item,
                        "row": issue.row,
                    }.items()
                    if v is not None
                }
                for issue in issues
            ],
        }
    }


def _issues_from_validation(error: RequestValidationError) -> list[Issue]:
    issues: list[Issue] = []
    for err in error.errors():
        loc = [p for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        field = ".".join(str(p) for p in loc if isinstance(p, str)) or None
        issues.append(
            Issue(
                code=str(err.get("type", "invalid")),
                message=str(err.get("msg", "Invalid field.")),
                field=field,
            )
        )
    return issues


def render_error(error: Exception) -> JSONResponse:
    if isinstance(error, ResultsError):
        status = next(
            code for cls, code in STATUS_BY_ERROR.items() if isinstance(error, cls)
        )
        return JSONResponse(error_body(error.code, error.message, error.issues), status_code=status)
    assert isinstance(error, RequestValidationError)
    return JSONResponse(
        error_body(
            "validation_failed",
            "The request has invalid fields.",
            _issues_from_validation(error),
        ),
        status_code=422,
    )


class ResultsRoute(APIRoute):
    """Translates domain refusals to HTTP error JSON and disables response caching."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def guarded(request: Request) -> Response:
            try:
                response = await handler(request)
            except (ResultsError, RequestValidationError) as exc:
                response = render_error(exc)
            except HTTPException:
                raise
            response.headers["Cache-Control"] = "no-store"
            return response

        return guarded
