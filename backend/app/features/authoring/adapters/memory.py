"""In-memory adapter for tests, fixtures and local demos.

Each unit of work operates on a deep copy of the store and swaps it in on
commit, so a failed transaction leaves zero changes, matching PostgreSQL.
A process-wide lock serializes transactions in place of row locks.
"""
from __future__ import annotations

import copy
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable
from uuid import UUID, uuid4

from ..domain import (
    AccountRecord, AssignedVersion, Enrollment, Exam, Question, QuestionVersion,
)
from ..ports import (
    AccountDirectory, BankQuery, EnrollmentRepository, ExamRepository, ProvisionedCandidate,
    QuestionRepository, UnitOfWork,
)


@dataclass
class MemoryStore:
    exams: dict[UUID, Exam] = field(default_factory=dict)
    questions: dict[UUID, Question] = field(default_factory=dict)
    enrollments: dict[tuple[UUID, UUID], Enrollment] = field(default_factory=dict)
    accounts: dict[UUID, AccountRecord] = field(default_factory=dict)

    def add_account(self, email: str, display_name: str, *roles: str,
                    enabled: bool = True, account_id: UUID | None = None) -> AccountRecord:
        record = AccountRecord(account_id or uuid4(), email, display_name, enabled,
                               frozenset(roles))
        self.accounts[record.id] = record
        return record


class _Exams(ExamRepository):
    def __init__(self, store: MemoryStore) -> None:
        self._s = store

    def get(self, exam_id, *, lock=False):
        return self._s.exams.get(exam_id)

    def add(self, exam):
        self._s.exams[exam.id] = exam

    def save(self, exam):
        self._s.exams[exam.id] = exam

    def owned_by(self, owner_id):
        return [e for e in self._s.exams.values() if e.owner_id == owner_id]

    def get_many(self, exam_ids):
        return [self._s.exams[i] for i in exam_ids if i in self._s.exams]


class _Questions(QuestionRepository):
    def __init__(self, store: MemoryStore) -> None:
        self._s = store

    def get(self, question_id, *, lock=False):
        return self._s.questions.get(question_id)

    def add(self, question):
        self._s.questions[question.id] = question

    def append_version(self, question, version):
        self._s.questions[question.id] = question

    def search(self, owner_id, query: BankQuery):
        text = query.text.strip().casefold()
        found = []
        for q in self._s.questions.values():
            c = q.latest.content
            if q.owner_id != owner_id:
                continue
            if query.topic and c.topic.casefold() != query.topic.strip().casefold():
                continue
            if query.difficulty and c.difficulty is not query.difficulty:
                continue
            if query.kind and c.kind is not query.kind:
                continue
            if text and text not in f"{c.prompt} {c.topic} {q.id}".casefold():
                continue
            found.append(q)
        return found

    def versions(self, version_ids):
        wanted, found = set(version_ids), {}
        for q in self._s.questions.values():
            for v in q.versions:
                if v.id in wanted:
                    found[v.id] = AssignedVersion(v, q.owner_id)
        return found


class _Enrollments(EnrollmentRepository):
    def __init__(self, store: MemoryStore) -> None:
        self._s = store

    def get(self, exam_id, candidate_id):
        return self._s.enrollments.get((exam_id, candidate_id))

    def add(self, enrollment):
        self._s.enrollments[(enrollment.exam_id, enrollment.candidate_id)] = enrollment

    save = add

    def for_exam(self, exam_id):
        return [e for (x, _), e in self._s.enrollments.items() if x == exam_id]

    def for_candidate(self, candidate_id):
        return [e for (_, c), e in self._s.enrollments.items() if c == candidate_id]


class _Accounts(AccountDirectory):
    def __init__(self, store: MemoryStore) -> None:
        self._s = store

    def by_email(self, email):
        key = email.strip().casefold()
        return next((a for a in self._s.accounts.values() if a.email.strip().casefold() == key),
                    None)

    def by_ids(self, account_ids: Iterable[UUID]):
        return {i: self._s.accounts[i] for i in account_ids if i in self._s.accounts}

    def provision_candidate(self, email, display_name):
        record = self._s.add_account(email.strip(), display_name.strip(), "candidate")
        return ProvisionedCandidate(record, secrets.token_urlsafe(12))


class MemoryUnitOfWork(UnitOfWork):
    _lock = threading.RLock()

    def __init__(self, store_ref: "MemoryDatabase") -> None:
        self._db = store_ref

    def __enter__(self):
        self._lock.acquire()
        self._working = copy.deepcopy(self._db.store)
        self.exams = _Exams(self._working)
        self.questions = _Questions(self._working)
        self.enrollments = _Enrollments(self._working)
        self.accounts = _Accounts(self._working)
        return self

    def __exit__(self, *exc):
        self._working = None
        self._lock.release()

    def now(self):
        return self._db.clock()

    def commit(self):
        self._db.store = self._working
        self._working = copy.deepcopy(self._working)
        self.exams._s = self.questions._s = self.enrollments._s = self.accounts._s = \
            self._working

    def rollback(self):
        self._working = copy.deepcopy(self._db.store)


class MemoryDatabase:
    """Holds the committed store and hands out units of work."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self.store = MemoryStore()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def unit_of_work(self) -> MemoryUnitOfWork:
        return MemoryUnitOfWork(self)
