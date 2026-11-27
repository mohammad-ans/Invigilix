"""Abstract repository, unit-of-work, and PDF rendering boundaries for results."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import TracebackType
from typing import Iterable
from uuid import UUID

from .domain import (
    AccountSummary,
    AnnouncementRecord,
    AttemptEventRecord,
    AttemptItemRecord,
    AttemptRecord,
    ClassSummary,
    EnrollmentRecord,
    ExamItemSpec,
    ExamRecord,
    QuestionAnalytics,
    ResultReportRecord,
)

ADMIN, EXAMINER, CANDIDATE = "admin", "examiner", "candidate"


@dataclass(frozen=True)
class Actor:
    """Authenticated caller resolved by the platform session dependency."""

    id: UUID
    roles: frozenset[str]
    enabled: bool = True

    def has(self, role: str) -> bool:
        return role in self.roles


@dataclass(frozen=True)
class CandidateScoreLine:
    """One candidate row inside an exported class summary."""

    attempt_id: UUID
    display_name: str
    email: str
    close_reason: str
    finalized_at: datetime
    graded_count: int
    item_count: int
    total_score: Decimal | None


@dataclass(frozen=True)
class CandidateReportItemLine:
    """Candidate-safe item line for personal PDF generation (keys/rubrics excluded)."""

    display_no: int
    slot: int
    kind: str
    prompt: str
    max_marks: Decimal
    awarded_marks: Decimal


class ExamReadWriteRepository(ABC):
    @abstractmethod
    def get(self, exam_id: UUID, *, lock: bool = False) -> ExamRecord | None: ...

    @abstractmethod
    def paper_items(self, exam_id: UUID) -> list[ExamItemSpec]: ...

    @abstractmethod
    def set_results_published(self, exam_id: UUID, published_at: datetime) -> ExamRecord: ...


class EnrollmentReadRepository(ABC):
    @abstractmethod
    def get(self, exam_id: UUID, candidate_id: UUID) -> EnrollmentRecord | None: ...

    @abstractmethod
    def for_exam(self, exam_id: UUID) -> list[EnrollmentRecord]: ...


class AttemptResultsRepository(ABC):
    @abstractmethod
    def get(self, attempt_id: UUID, *, lock: bool = False) -> AttemptRecord | None: ...

    @abstractmethod
    def for_exam(self, exam_id: UUID) -> list[AttemptRecord]: ...

    @abstractmethod
    def items_for_attempt(self, attempt_id: UUID) -> list[AttemptItemRecord]: ...

    @abstractmethod
    def items_for_exam(self, exam_id: UUID) -> dict[UUID, list[AttemptItemRecord]]: ...

    @abstractmethod
    def set_item_award(
        self,
        attempt_id: UUID,
        slot: int,
        awarded_marks: Decimal,
        graded_by: UUID,
    ) -> AttemptItemRecord: ...

    @abstractmethod
    def events_for_exam(self, exam_id: UUID) -> list[AttemptEventRecord]: ...


class AnnouncementRepository(ABC):
    @abstractmethod
    def for_exam(self, exam_id: UUID) -> list[AnnouncementRecord]: ...

    @abstractmethod
    def add(self, announcement: AnnouncementRecord) -> None: ...


class ReportRepository(ABC):
    @abstractmethod
    def get_by_attempt(self, attempt_id: UUID) -> ResultReportRecord | None: ...

    @abstractmethod
    def get_by_code(self, verification_code: str) -> ResultReportRecord | None: ...

    @abstractmethod
    def for_exam(self, exam_id: UUID) -> dict[UUID, ResultReportRecord]: ...

    @abstractmethod
    def add(self, report: ResultReportRecord) -> None: ...


class AccountLookup(ABC):
    @abstractmethod
    def by_ids(self, account_ids: Iterable[UUID]) -> dict[UUID, AccountSummary]: ...


class PdfRenderer(ABC):
    """Render deterministic printable PDF reports without external paid services."""

    @abstractmethod
    def render_candidate_report(
        self,
        *,
        exam: ExamRecord,
        attempt: AttemptRecord,
        candidate: AccountSummary,
        total_score: Decimal,
        verification_code: str,
        issued_at: datetime,
        items: list[CandidateReportItemLine],
    ) -> bytes: ...

    @abstractmethod
    def render_class_summary(
        self,
        *,
        exam: ExamRecord,
        generated_at: datetime,
        status: str,
        summary: ClassSummary,
        candidates: list[CandidateScoreLine],
        analytics: list[QuestionAnalytics],
    ) -> bytes: ...


class ResultsUnitOfWork(ABC):
    """Transactional unit of work for results, monitoring, grading, and reports."""

    exams: ExamReadWriteRepository
    enrollments: EnrollmentReadRepository
    attempts: AttemptResultsRepository
    announcements: AnnouncementRepository
    reports: ReportRepository
    accounts: AccountLookup

    @abstractmethod
    def now(self) -> datetime:
        """Authoritative UTC database timestamp read inside the active transaction."""

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...

    def __enter__(self) -> "ResultsUnitOfWork":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.rollback()
