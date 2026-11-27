"""In-memory transactional unit-of-work and store for isolated tests and fixtures."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Iterable
from uuid import UUID

from ..domain import (
    AccountSummary,
    AnnouncementRecord,
    AttemptEventRecord,
    AttemptItemRecord,
    AttemptRecord,
    EnrollmentRecord,
    ExamItemSpec,
    ExamRecord,
    ResultReportRecord,
    quantize_marks,
)
from ..ports import (
    AccountLookup,
    AnnouncementRepository,
    AttemptResultsRepository,
    EnrollmentReadRepository,
    ExamReadWriteRepository,
    ReportRepository,
    ResultsUnitOfWork,
)


class InMemoryResultsStore:
    """Mutable state store cloned per uncommitted transaction for rollback isolation."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.accounts: dict[UUID, AccountSummary] = {}
        self.exams: dict[UUID, ExamRecord] = {}
        self.paper_items: dict[UUID, list[ExamItemSpec]] = {}
        self.enrollments: dict[tuple[UUID, UUID], EnrollmentRecord] = {}
        self.attempts: dict[UUID, AttemptRecord] = {}
        self.attempt_items: dict[UUID, list[AttemptItemRecord]] = {}
        self.attempt_events: list[AttemptEventRecord] = []
        self.announcements: list[AnnouncementRecord] = []
        self.reports_by_code: dict[str, ResultReportRecord] = {}

    def uow(self) -> "InMemoryResultsUnitOfWork":
        return InMemoryResultsUnitOfWork(self)


class _MemExamRepo(ExamReadWriteRepository):
    def __init__(self, state: dict) -> None:
        self._state = state

    def get(self, exam_id: UUID, *, lock: bool = False) -> ExamRecord | None:
        return self._state["exams"].get(exam_id)

    def paper_items(self, exam_id: UUID) -> list[ExamItemSpec]:
        return sorted(self._state["paper_items"].get(exam_id, ()), key=lambda s: s.slot)

    def set_results_published(self, exam_id: UUID, published_at: datetime) -> ExamRecord:
        current = self._state["exams"][exam_id]
        updated = replace(current, results_published_at=published_at)
        self._state["exams"][exam_id] = updated
        return updated


class _MemEnrollmentRepo(EnrollmentReadRepository):
    def __init__(self, state: dict) -> None:
        self._state = state

    def get(self, exam_id: UUID, candidate_id: UUID) -> EnrollmentRecord | None:
        return self._state["enrollments"].get((exam_id, candidate_id))

    def for_exam(self, exam_id: UUID) -> list[EnrollmentRecord]:
        return [e for (eid, _), e in self._state["enrollments"].items() if eid == exam_id]


class _MemAttemptRepo(AttemptResultsRepository):
    def __init__(self, state: dict) -> None:
        self._state = state

    def get(self, attempt_id: UUID, *, lock: bool = False) -> AttemptRecord | None:
        return self._state["attempts"].get(attempt_id)

    def for_exam(self, exam_id: UUID) -> list[AttemptRecord]:
        return [a for a in self._state["attempts"].values() if a.exam_id == exam_id]

    def items_for_attempt(self, attempt_id: UUID) -> list[AttemptItemRecord]:
        return sorted(self._state["attempt_items"].get(attempt_id, ()), key=lambda it: it.slot)

    def items_for_exam(self, exam_id: UUID) -> dict[UUID, list[AttemptItemRecord]]:
        return {
            a.id: self.items_for_attempt(a.id)
            for a in self._state["attempts"].values()
            if a.exam_id == exam_id
        }

    def set_item_award(
        self,
        attempt_id: UUID,
        slot: int,
        awarded_marks: Decimal,
        graded_by: UUID,
    ) -> AttemptItemRecord:
        items = self._state["attempt_items"][attempt_id]
        for idx, it in enumerate(items):
            if it.slot == slot:
                updated = replace(
                    it,
                    awarded_marks=quantize_marks(awarded_marks),
                    graded_by=graded_by,
                )
                items[idx] = updated
                return updated
        raise KeyError((attempt_id, slot))

    def events_for_exam(self, exam_id: UUID) -> list[AttemptEventRecord]:
        attempt_ids = {a.id for a in self._state["attempts"].values() if a.exam_id == exam_id}
        return [ev for ev in self._state["attempt_events"] if ev.attempt_id in attempt_ids]


class _MemAnnouncementRepo(AnnouncementRepository):
    def __init__(self, state: dict) -> None:
        self._state = state

    def for_exam(self, exam_id: UUID) -> list[AnnouncementRecord]:
        return [a for a in self._state["announcements"] if a.exam_id == exam_id]

    def add(self, announcement: AnnouncementRecord) -> None:
        self._state["announcements"].append(announcement)


class _MemReportRepo(ReportRepository):
    def __init__(self, state: dict) -> None:
        self._state = state

    def get_by_attempt(self, attempt_id: UUID) -> ResultReportRecord | None:
        return next(
            (r for r in self._state["reports_by_code"].values() if r.attempt_id == attempt_id),
            None,
        )

    def get_by_code(self, verification_code: str) -> ResultReportRecord | None:
        return self._state["reports_by_code"].get(verification_code)

    def for_exam(self, exam_id: UUID) -> dict[UUID, ResultReportRecord]:
        attempt_ids = {a.id for a in self._state["attempts"].values() if a.exam_id == exam_id}
        return {
            r.attempt_id: r
            for r in self._state["reports_by_code"].values()
            if r.attempt_id in attempt_ids
        }

    def add(self, report: ResultReportRecord) -> None:
        if report.verification_code in self._state["reports_by_code"]:
            raise ValueError("Duplicate verification code.")
        if any(r.attempt_id == report.attempt_id for r in self._state["reports_by_code"].values()):
            raise ValueError("Duplicate report for attempt.")
        self._state["reports_by_code"][report.verification_code] = report


class _MemAccountLookup(AccountLookup):
    def __init__(self, state: dict) -> None:
        self._state = state

    def by_ids(self, account_ids: Iterable[UUID]) -> dict[UUID, AccountSummary]:
        return {
            aid: self._state["accounts"][aid]
            for aid in account_ids
            if aid in self._state["accounts"]
        }


class InMemoryResultsUnitOfWork(ResultsUnitOfWork):
    """Snapshot-isolated in-memory transaction matching SQL commit/rollback behavior."""

    def __init__(self, store: InMemoryResultsStore) -> None:
        self._store = store
        self._committed = False
        self._state = {
            "accounts": deepcopy(store.accounts),
            "exams": deepcopy(store.exams),
            "paper_items": deepcopy(store.paper_items),
            "enrollments": deepcopy(store.enrollments),
            "attempts": deepcopy(store.attempts),
            "attempt_items": deepcopy(store.attempt_items),
            "attempt_events": deepcopy(store.attempt_events),
            "announcements": deepcopy(store.announcements),
            "reports_by_code": deepcopy(store.reports_by_code),
        }
        self.exams = _MemExamRepo(self._state)
        self.enrollments = _MemEnrollmentRepo(self._state)
        self.attempts = _MemAttemptRepo(self._state)
        self.announcements = _MemAnnouncementRepo(self._state)
        self.reports = _MemReportRepo(self._state)
        self.accounts = _MemAccountLookup(self._state)

    def now(self) -> datetime:
        return self._store.clock().astimezone(timezone.utc)

    def commit(self) -> None:
        self._store.accounts = self._state["accounts"]
        self._store.exams = self._state["exams"]
        self._store.paper_items = self._state["paper_items"]
        self._store.enrollments = self._state["enrollments"]
        self._store.attempts = self._state["attempts"]
        self._store.attempt_items = self._state["attempt_items"]
        self._store.attempt_events = self._state["attempt_events"]
        self._store.announcements = self._state["announcements"]
        self._store.reports_by_code = self._state["reports_by_code"]
        self._committed = True

    def rollback(self) -> None:
        pass

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None or not self._committed:
            self.rollback()
