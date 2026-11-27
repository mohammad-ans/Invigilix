"""Uniform error bodies for the authoring router.

``AuthoringRoute`` catches domain refusals and request validation failures
raised inside a handler and renders::

    {"error": {"code": "...", "message": "...", "issues": [{"field", "item", "row", ...}]}}

It also marks every authoring response ``Cache-Control: no-store`` because
examiner payloads contain private keys and rubrics (NFR01).
"""
from __future__ import annotations

from typing import Any, Callable, Coroutine

from fastapi import HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from ..domain import AuthoringError, Conflict, Forbidden, Issue, NotFound, ValidationFailed

STATUS: dict[type[AuthoringError], int] = {
    ValidationFailed: 422, NotFound: 404, Forbidden: 403, Conflict: 409,
}


def error_body(code: str, message: str, issues: tuple[Issue, ...] | list[Issue] = ()) -> dict:
    return {"error": {"code": code, "message": message,
                      "issues": [{k: v for k, v in i.__dict__.items()} for i in issues]}}


def from_request_validation(error: RequestValidationError) -> list[Issue]:
    issues = []
    for detail in error.errors():
        location = [str(p) for p in detail.get("loc", ()) if p not in ("body", "query", "path")]
        item = None
        if len(location) >= 2 and location[0] == "items" and location[1].isdigit():
            item = int(location[1]) + 1  # slots are 1-based
        issues.append(Issue(detail.get("type", "invalid"), detail.get("msg", "Invalid value."),
                            field=location[-1] if location else None, item=item))
    return issues


def render(error: Exception) -> JSONResponse:
    if isinstance(error, AuthoringError):
        status = next(s for cls, s in STATUS.items() if isinstance(error, cls))
        return JSONResponse(error_body(error.code, error.message, error.issues), status)
    assert isinstance(error, RequestValidationError)
    return JSONResponse(error_body("validation_failed", "The request has invalid fields.",
                                   from_request_validation(error)), 422)


class AuthoringRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def guarded(request: Request) -> Response:
            try:
                response = await handler(request)
            except (AuthoringError, RequestValidationError) as error:
                response = render(error)
            except HTTPException:
                raise
            response.headers["Cache-Control"] = "no-store"
            return response

        return guarded
