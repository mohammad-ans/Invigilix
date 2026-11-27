"""Domain failures for the results, monitoring, grading, and verification feature."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable


@dataclass(frozen=True)
class Issue:
    """One actionable validation or state-transition finding."""

    code: str
    message: str
    field: str | None = None
    item: int | None = None
    row: int | None = None

    def located(self, **where: int | str | None) -> "Issue":
        return replace(self, **where)


class ResultsError(Exception):
    """Base exception for results domain and service refusals."""

    def __init__(self, code: str, message: str, issues: Iterable[Issue] = ()) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.issues = tuple(issues)


class ValidationFailed(ResultsError):
    """Input is malformed or violates field bounds (HTTP 422)."""

    def __init__(
        self,
        issues: Iterable[Issue],
        message: str = "The request has invalid fields.",
        code: str = "validation_failed",
    ) -> None:
        super().__init__(code, message, issues)


class NotFound(ResultsError):
    """Record is absent or private to another owner/candidate (HTTP 404)."""

    def __init__(self, what: str = "Resource") -> None:
        super().__init__("not_found", f"{what} was not found.")


class Forbidden(ResultsError):
    """Authenticated caller lacks the required role for this action (HTTP 403)."""

    def __init__(self, message: str = "Your role does not permit this action.") -> None:
        super().__init__("forbidden", message)


class Conflict(ResultsError):
    """Action is invalid in the record's current lifecycle state (HTTP 409)."""
