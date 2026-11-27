"""Exam aggregate: a draft that becomes a frozen, publishable paper."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Mapping
from uuid import UUID

from .errors import Conflict, Issue, ValidationFailed
from .values import ExamSchedule, parse_marks

if TYPE_CHECKING:
    from .publication import AssignedVersion, PublicationPolicy, PublicationReport


class ExamState(StrEnum):
    """Effective state derived from publication, the window and database time."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"  # published before opening
    ONGOING = "ongoing"
    COMPLETED = "completed"


@dataclass(frozen=True)
class ExamDetails:
    """The examiner-editable particulars of an exam (FR03)."""

    title: str
    instructions: str
    schedule: ExamSchedule
    total_marks: Decimal
    shuffle_questions: bool = False
    shuffle_choices: bool = False

    @classmethod
    def build(cls, *, title: str, instructions: str, opens_at: datetime, closes_at: datetime,
              duration_minutes: int, total_marks: object, shuffle_questions: bool = False,
              shuffle_choices: bool = False) -> "ExamDetails":
        """Validate raw particulars, reporting every broken rule at once."""
        issues: list[Issue] = []
        if not title.strip():
            issues.append(Issue("required", "Enter a title.", field="title"))
        schedule = ExamSchedule(opens_at, closes_at, timedelta(minutes=duration_minutes))
        issues.extend(schedule.issues())
        total, total_issue = parse_marks(total_marks, "total_marks")
        if total_issue:
            issues.append(total_issue)
        if issues:
            raise ValidationFailed(issues)
        assert total is not None
        return cls(title.strip(), instructions.strip(), schedule, total,
                   shuffle_questions, shuffle_choices)


@dataclass(frozen=True)
class PaperItem:
    """One slot of the paper, pinned to an exact question version and cap."""

    slot: int
    question_id: UUID
    version_id: UUID
    max_marks: Decimal


@dataclass
class Exam:
    """Aggregate root. Every mutation is refused once the paper is published."""

    id: UUID
    owner_id: UUID
    details: ExamDetails
    items: tuple[PaperItem, ...] = field(default_factory=tuple)
    published_at: datetime | None = None

    @property
    def is_published(self) -> bool:
        return self.published_at is not None

    @property
    def allocated_marks(self) -> Decimal:
        return sum((i.max_marks for i in self.items), Decimal("0.00"))

    def owned_by(self, account_id: UUID) -> bool:
        return self.owner_id == account_id

    def state_at(self, now: datetime) -> ExamState:
        if not self.is_published:
            return ExamState.DRAFT
        schedule = self.details.schedule
        if now < schedule.opens_at:
            return ExamState.SCHEDULED
        if now < schedule.closes_at:
            return ExamState.ONGOING
        return ExamState.COMPLETED

    def revise(self, details: ExamDetails) -> None:
        self._ensure_draft()
        self.details = details

    def assign(self, items: list[PaperItem]) -> None:
        """Replace the draft's slot list. Totals may still mismatch until publish."""
        self._ensure_draft()
        issues: list[Issue] = []
        if [i.slot for i in items] != list(range(1, len(items) + 1)):
            issues.append(Issue("slot_order", "Slots must be numbered 1, 2, 3 … in order.",
                                field="items"))
        seen: set[UUID] = set()
        for item in items:
            if item.question_id in seen:
                issues.append(Issue("duplicate_question",
                                    "This bank question already appears on the paper.",
                                    field="question_id", item=item.slot))
            seen.add(item.question_id)
            if item.max_marks <= 0:
                issues.append(Issue("non_positive_marks", "Marks must be greater than zero.",
                                    field="max_marks", item=item.slot))
        if issues:
            raise ValidationFailed(issues)
        self.items = tuple(items)

    def publish(self, now: datetime, bank: Mapping[UUID, "AssignedVersion"],
                policy: "PublicationPolicy") -> "PublicationReport":
        """Freeze slots, versions, caps, schedule and settings (FR05)."""
        self._ensure_draft()
        report = policy.review(self, bank, now)
        if not report.ready:
            raise ValidationFailed(report.issues, "The paper cannot be published yet.",
                                   code="paper_invalid")
        self.published_at = now
        return report

    def duplicate(self, new_id: UUID, owner_id: UUID) -> "Exam":
        """A new draft with the same particulars and pinned versions.

        Works from any state, so a frozen paper can seed next term's exam.
        The copy keeps the exact versions; the editor offers re-pinning.
        """
        title = f"Copy of {self.details.title}"[:300]
        details = ExamDetails(title, self.details.instructions, self.details.schedule,
                              self.details.total_marks, self.details.shuffle_questions,
                              self.details.shuffle_choices)
        return Exam(new_id, owner_id, details, tuple(self.items))

    def _ensure_draft(self) -> None:
        if self.is_published:
            raise Conflict("exam_published",
                           "This paper is published and frozen. It can no longer be edited.")
