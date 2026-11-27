"""Read models returned by the services. The API serializes these; nothing mutates them."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ..domain import (
    AccountRecord, CandidateItem, EntryDecision, Enrollment, Exam, ExamState, PaperItem,
    PublicationReport, QuestionVersion,
)


@dataclass(frozen=True)
class SlotView:
    item: PaperItem
    version: QuestionVersion
    latest_number: int

    @property
    def outdated(self) -> bool:
        """A newer bank version exists; the slot keeps the pinned one."""
        return self.latest_number > self.version.number


@dataclass(frozen=True)
class ExamOverview:
    exam: Exam
    state: ExamState
    slots: tuple[SlotView, ...]
    report: PublicationReport
    server_time: datetime


@dataclass(frozen=True)
class ExamSummary:
    exam: Exam
    state: ExamState
    enrolled: int

    @property
    def allocated_marks(self) -> Decimal:
        return self.exam.allocated_marks


@dataclass(frozen=True)
class QuestionUsage:
    exam_id: object
    exam_title: str
    slot: int
    version_number: int
    frozen: bool


@dataclass(frozen=True)
class RosterEntry:
    account: AccountRecord
    enrollment: Enrollment
    decision: EntryDecision


@dataclass(frozen=True)
class RosterView:
    exam: Exam
    state: ExamState
    entries: tuple[RosterEntry, ...]
    server_time: datetime


@dataclass(frozen=True)
class CandidateExamEntry:
    """One assigned exam as a candidate may see it: metadata, never questions."""

    exam: Exam
    decision: EntryDecision


@dataclass(frozen=True)
class SandboxPaper:
    """A transient preview. It has no attempt ID and is never persisted (SR03)."""

    exam: Exam
    items: tuple[CandidateItem, ...]
    server_time: datetime
    deadline_at: datetime
