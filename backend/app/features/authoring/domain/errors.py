"""Authoring failures expressed in domain terms.

The HTTP layer maps each class to one status code. Every error carries a stable
``code`` plus zero or more :class:`Issue` records that point at the offending
field, paper slot or CSV row so the UI can place feedback next to the input.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable


@dataclass(frozen=True)
class Issue:
    """One precise validation finding."""

    code: str
    message: str
    field: str | None = None
    item: int | None = None
    row: int | None = None

    def located(self, **where: int | str | None) -> "Issue":
        """Return a copy that also records where the issue occurred."""
        return replace(self, **where)


class AuthoringError(Exception):
    """Base class for refusals raised by the authoring feature."""

    def __init__(self, code: str, message: str, issues: Iterable[Issue] = ()) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.issues = tuple(issues)


class ValidationFailed(AuthoringError):
    """Input is well-formed but breaks a rule (HTTP 422)."""

    def __init__(self, issues: Iterable[Issue], message: str = "The request has invalid fields.",
                 code: str = "validation_failed") -> None:
        super().__init__(code, message, issues)


class NotFound(AuthoringError):
    """The record does not exist or the actor may not know it exists (HTTP 404)."""

    def __init__(self, what: str) -> None:
        super().__init__("not_found", f"{what} was not found.")


class Forbidden(AuthoringError):
    """The actor's current role does not permit the action (HTTP 403)."""

    def __init__(self, message: str = "Your role does not permit this action.") -> None:
        super().__init__("forbidden", message)


class Conflict(AuthoringError):
    """The action is invalid for the record's current state (HTTP 409)."""
