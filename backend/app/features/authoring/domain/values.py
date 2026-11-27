"""Value objects shared by the authoring aggregates."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum

from .errors import Issue

MARK_QUANTUM = Decimal("0.01")
MARK_CEILING = Decimal("999999.99")  # NUMERIC(8,2)


class QuestionKind(StrEnum):
    SINGLE = "single"
    MULTIPLE = "multiple"
    WRITTEN = "written"

    @property
    def objective(self) -> bool:
        return self is not QuestionKind.WRITTEN


class MarkingRule(StrEnum):
    EXACT = "exact"
    PARTIAL_NO_WRONG = "partial_no_wrong"
    MANUAL = "manual"


class Change(StrEnum):
    """What a write did to a record. Reported back so reruns can prove idempotence."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


#: Mirrors the CHECK constraint on ``question_version``.
ALLOWED_RULES: dict[QuestionKind, frozenset[MarkingRule]] = {
    QuestionKind.SINGLE: frozenset({MarkingRule.EXACT}),
    QuestionKind.MULTIPLE: frozenset({MarkingRule.EXACT, MarkingRule.PARTIAL_NO_WRONG}),
    QuestionKind.WRITTEN: frozenset({MarkingRule.MANUAL}),
}


def parse_marks(value: object, field: str) -> tuple[Decimal | None, Issue | None]:
    """Parse a positive mark value with at most two decimal places.

    Marks are stored as NUMERIC(8,2); refusing extra precision avoids silently
    rounding a cap that the examiner believes sums to the declared total.
    """
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None, Issue("invalid_marks", "Enter marks as a number.", field=field)
    if not amount.is_finite():
        return None, Issue("invalid_marks", "Enter marks as a number.", field=field)
    if amount <= 0:
        return None, Issue("non_positive_marks", "Marks must be greater than zero.", field=field)
    if amount != amount.quantize(MARK_QUANTUM, rounding=ROUND_HALF_UP):
        return None, Issue("marks_precision", "Use at most two decimal places.", field=field)
    if amount > MARK_CEILING:
        return None, Issue("marks_too_large", "Marks exceed the supported maximum.", field=field)
    return amount.quantize(MARK_QUANTUM), None


def require_marks(value: object, field: str) -> Decimal:
    from .errors import ValidationFailed

    amount, issue = parse_marks(value, field)
    if issue:
        raise ValidationFailed([issue])
    assert amount is not None
    return amount


@dataclass(frozen=True)
class ExamSchedule:
    """The exam window and the per-attempt working time."""

    opens_at: datetime
    closes_at: datetime
    duration: timedelta

    def issues(self) -> list[Issue]:
        found: list[Issue] = []
        for name in ("opens_at", "closes_at"):
            if getattr(self, name).utcoffset() is None:
                found.append(Issue("timezone_required", "Include a time-zone offset.", field=name))
        comparable = not found
        if self.duration <= timedelta(0):
            found.append(Issue("non_positive_duration", "Duration must be greater than zero.",
                               field="duration_minutes"))
        if comparable and self.closes_at <= self.opens_at:
            found.append(Issue("close_before_open", "The exam must close after it opens.",
                               field="closes_at"))
        return found

    def is_open_at(self, now: datetime) -> bool:
        return self.opens_at <= now < self.closes_at

    @property
    def duration_seconds(self) -> int:
        return int(self.duration.total_seconds())
