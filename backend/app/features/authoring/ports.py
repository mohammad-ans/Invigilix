"""Abstract boundaries the authoring services depend on.

The platform supplies concrete implementations: the SQLAlchemy adapter for
production, the in-memory adapter for tests and fixtures. Identity (accounts,
password hashing, sessions) belongs to the foundation; authoring only reads
accounts and asks the identity service to provision imported candidates.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Iterable
from uuid import UUID

from .domain import (
    AccountRecord, AssignedVersion, Difficulty, Enrollment, Exam, Question, QuestionKind,
    QuestionVersion,
)

ADMIN, EXAMINER, CANDIDATE = "admin", "examiner", "candidate"


@dataclass(frozen=True)
class Actor:
    """The authenticated caller, resolved by the platform from the session."""

    id: UUID
    roles: frozenset[str]

    def has(self, role: str) -> bool:
        return role in self.roles


@dataclass(frozen=True)
class BankQuery:
    text: str = ""
    topic: str = ""
    difficulty: Difficulty | None = None
    kind: QuestionKind | None = None


@dataclass(frozen=True)
class ProvisionedCandidate:
    """A new candidate account and its one-time initial credential."""

    account: AccountRecord
    initial_password: str


class ExamRepository(ABC):
    @abstractmethod
    def get(self, exam_id: UUID, *, lock: bool = False) -> Exam | None: ...

    @abstractmethod
    def add(self, exam: Exam) -> None: ...

    @abstractmethod
    def save(self, exam: Exam) -> None: ...

    @abstractmethod
    def owned_by(self, owner_id: UUID) -> list[Exam]: ...

    @abstractmethod
    def get_many(self, exam_ids: Iterable[UUID]) -> list[Exam]: ...


class QuestionRepository(ABC):
    @abstractmethod
    def get(self, question_id: UUID, *, lock: bool = False) -> Question | None: ...

    @abstractmethod
    def add(self, question: Question) -> None: ...

    @abstractmethod
    def append_version(self, question: Question, version: QuestionVersion) -> None: ...

    @abstractmethod
    def search(self, owner_id: UUID, query: BankQuery) -> list[Question]: ...

    @abstractmethod
    def versions(self, version_ids: Iterable[UUID]) -> dict[UUID, AssignedVersion]: ...


class EnrollmentRepository(ABC):
    @abstractmethod
    def get(self, exam_id: UUID, candidate_id: UUID) -> Enrollment | None: ...

    @abstractmethod
    def add(self, enrollment: Enrollment) -> None: ...

    @abstractmethod
    def save(self, enrollment: Enrollment) -> None: ...

    @abstractmethod
    def for_exam(self, exam_id: UUID) -> list[Enrollment]: ...

    @abstractmethod
    def for_candidate(self, candidate_id: UUID) -> list[Enrollment]: ...


class AccountDirectory(ABC):
    """Read access to accounts plus candidate provisioning (foundation identity)."""

    @abstractmethod
    def by_email(self, email: str) -> AccountRecord | None: ...

    @abstractmethod
    def by_ids(self, account_ids: Iterable[UUID]) -> dict[UUID, AccountRecord]: ...

    @abstractmethod
    def provision_candidate(self, email: str, display_name: str) -> ProvisionedCandidate: ...


class UnitOfWork(ABC):
    """One database transaction. Leaving the block without ``commit`` rolls back."""

    exams: ExamRepository
    questions: QuestionRepository
    enrollments: EnrollmentRepository
    accounts: AccountDirectory

    @abstractmethod
    def now(self) -> datetime:
        """Authoritative server time, read inside the transaction."""

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...

    def __enter__(self) -> "UnitOfWork":
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 tb: TracebackType | None) -> None:
        self.rollback()
