"""SQLAlchemy implementation of the authoring ports over the contract schema.

Locks follow the schema's transaction notes: ``lock=True`` issues
``SELECT … FOR UPDATE`` on PostgreSQL. ``now()`` reads ``clock_timestamp()``
inside the transaction so publication and eligibility use database time.
"""
from __future__ import annotations

import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Iterable
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, delete, func, insert, or_, select, update

from ..domain import (
    AccountRecord, AnswerOption, AssignedVersion, Difficulty, Enrollment, Exam, ExamDetails,
    ExamSchedule, MarkingRule, PaperItem, Question, QuestionContent, QuestionKind, QuestionVersion,
)
from ..ports import (
    AccountDirectory, BankQuery, EnrollmentRepository, ExamRepository, ProvisionedCandidate,
    QuestionRepository, UnitOfWork,
)
from . import sql_tables as t

CENT = Decimal("0.01")


def _marks(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT)


class _Repo:
    def __init__(self, conn: Connection) -> None:
        self._c = conn

    def _locked(self, statement, lock: bool):
        if lock and self._c.dialect.name == "postgresql":
            return statement.with_for_update()
        return statement


class SqlQuestions(_Repo, QuestionRepository):
    def _versions_for(self, question_ids: list[UUID]) -> dict[UUID, list[QuestionVersion]]:
        if not question_ids:
            return {}
        rows = self._c.execute(select(t.question_version)
                               .where(t.question_version.c.question_id.in_(question_ids))
                               .order_by(t.question_version.c.version_no)).all()
        options = self._options([r.id for r in rows])
        found: dict[UUID, list[QuestionVersion]] = defaultdict(list)
        for r in rows:
            found[r.question_id].append(self._version(r, options[r.id]))
        return found

    def _options(self, version_ids: list[UUID]) -> dict[UUID, list[AnswerOption]]:
        found: dict[UUID, list[AnswerOption]] = defaultdict(list)
        if version_ids:
            for o in self._c.execute(select(t.question_option)
                                     .where(t.question_option.c.version_id.in_(version_ids))
                                     .order_by(t.question_option.c.option_no)):
                found[o.version_id].append(AnswerOption(o.option_no, o.label, o.is_correct))
        return found

    @staticmethod
    def _version(r, options: list[AnswerOption]) -> QuestionVersion:
        return QuestionVersion(r.id, r.question_id, r.version_no, QuestionContent(
            r.topic, Difficulty(r.difficulty), QuestionKind(r.kind), r.prompt,
            MarkingRule(r.marking_rule), tuple(options), r.rubric))

    def _load(self, rows) -> list[Question]:
        versions = self._versions_for([r.id for r in rows])
        return [Question(r.id, r.owner_id, versions[r.id]) for r in rows]

    def get(self, question_id, *, lock=False):
        row = self._c.execute(self._locked(select(t.question).where(t.question.c.id == question_id),
                                           lock)).first()
        return self._load([row])[0] if row else None

    def add(self, question):
        self._c.execute(insert(t.question).values(id=question.id, owner_id=question.owner_id))
        for version in question.versions:
            self.append_version(question, version)

    def append_version(self, question, version):
        c = version.content
        self._c.execute(insert(t.question_version).values(
            id=version.id, question_id=question.id, version_no=version.number, topic=c.topic,
            difficulty=c.difficulty.value, prompt=c.prompt, kind=c.kind.value,
            marking_rule=c.marking_rule.value, rubric=c.rubric))
        if c.options:
            self._c.execute(insert(t.question_option), [
                dict(version_id=version.id, option_no=o.id, label=o.label, is_correct=o.correct)
                for o in c.options])

    def search(self, owner_id, query: BankQuery):
        qv = t.question_version
        latest = (select(qv.c.question_id, func.max(qv.c.version_no).label("n"))
                  .group_by(qv.c.question_id).subquery())
        statement = (select(t.question)
                     .join(latest, latest.c.question_id == t.question.c.id)
                     .join(qv, (qv.c.question_id == latest.c.question_id)
                           & (qv.c.version_no == latest.c.n))
                     .where(t.question.c.owner_id == owner_id))
        if query.topic.strip():
            statement = statement.where(func.lower(qv.c.topic) == query.topic.strip().lower())
        if query.difficulty:
            statement = statement.where(qv.c.difficulty == query.difficulty.value)
        if query.kind:
            statement = statement.where(qv.c.kind == query.kind.value)
        if query.text.strip():
            pattern = "%" + query.text.strip().lower().replace("%", r"\%").replace("_", r"\_") + "%"
            statement = statement.where(or_(func.lower(qv.c.prompt).like(pattern, escape="\\"),
                                            func.lower(qv.c.topic).like(pattern, escape="\\")))
        return self._load(self._c.execute(statement).all())

    def versions(self, version_ids: Iterable[UUID]):
        ids = list(version_ids)
        if not ids:
            return {}
        rows = self._c.execute(select(t.question_version, t.question.c.owner_id)
                               .join(t.question, t.question.c.id == t.question_version.c.question_id)
                               .where(t.question_version.c.id.in_(ids))).all()
        options = self._options([r.id for r in rows])
        return {r.id: AssignedVersion(self._version(r, options[r.id]), r.owner_id) for r in rows}


class SqlExams(_Repo, ExamRepository):
    def _items(self, exam_ids: list[UUID]) -> dict[UUID, list[PaperItem]]:
        found: dict[UUID, list[PaperItem]] = defaultdict(list)
        if exam_ids:
            rows = self._c.execute(
                select(t.exam_item, t.question_version.c.question_id)
                .join(t.question_version, t.question_version.c.id == t.exam_item.c.version_id)
                .where(t.exam_item.c.exam_id.in_(exam_ids)).order_by(t.exam_item.c.slot))
            for r in rows:
                found[r.exam_id].append(PaperItem(r.slot, r.question_id, r.version_id,
                                                  _marks(r.max_marks)))
        return found

    def _load(self, rows) -> list[Exam]:
        items = self._items([r.id for r in rows])
        return [Exam(r.id, r.owner_id, ExamDetails(
            r.title, r.instructions,
            ExamSchedule(r.opens_at, r.closes_at, timedelta(seconds=r.duration_seconds)),
            _marks(r.total_marks), r.shuffle_objective, r.shuffle_choices),
            tuple(items[r.id]), r.published_at) for r in rows]

    @staticmethod
    def _row(exam: Exam) -> dict:
        d = exam.details
        return dict(owner_id=exam.owner_id, title=d.title, instructions=d.instructions,
                    opens_at=d.schedule.opens_at, closes_at=d.schedule.closes_at,
                    duration_seconds=d.schedule.duration_seconds, total_marks=d.total_marks,
                    shuffle_objective=d.shuffle_questions, shuffle_choices=d.shuffle_choices,
                    published_at=exam.published_at)

    def get(self, exam_id, *, lock=False):
        row = self._c.execute(self._locked(select(t.exam).where(t.exam.c.id == exam_id),
                                           lock)).first()
        return self._load([row])[0] if row else None

    def add(self, exam):
        self._c.execute(insert(t.exam).values(id=exam.id, **self._row(exam)))
        self._write_items(exam)

    def save(self, exam):
        self._c.execute(update(t.exam).where(t.exam.c.id == exam.id).values(**self._row(exam)))
        if tuple(self._items([exam.id])[exam.id]) != exam.items:
            self._c.execute(delete(t.exam_item).where(t.exam_item.c.exam_id == exam.id))
            self._write_items(exam)

    def _write_items(self, exam: Exam) -> None:
        if exam.items:
            self._c.execute(insert(t.exam_item), [
                dict(exam_id=exam.id, slot=i.slot, version_id=i.version_id, max_marks=i.max_marks)
                for i in exam.items])

    def owned_by(self, owner_id):
        return self._load(self._c.execute(select(t.exam).where(t.exam.c.owner_id == owner_id)).all())

    def get_many(self, exam_ids):
        ids = list(exam_ids)
        if not ids:
            return []
        return self._load(self._c.execute(select(t.exam).where(t.exam.c.id.in_(ids))).all())


class SqlEnrollments(_Repo, EnrollmentRepository):
    @staticmethod
    def _of(r) -> Enrollment:
        return Enrollment(r.exam_id, r.candidate_id, r.enrolled_by, r.active)

    def get(self, exam_id, candidate_id):
        row = self._c.execute(select(t.enrollment).where(
            (t.enrollment.c.exam_id == exam_id) & (t.enrollment.c.candidate_id == candidate_id))
        ).first()
        return self._of(row) if row else None

    def add(self, enrollment):
        self._c.execute(insert(t.enrollment).values(**enrollment.__dict__))

    def save(self, enrollment):
        self._c.execute(update(t.enrollment).where(
            (t.enrollment.c.exam_id == enrollment.exam_id)
            & (t.enrollment.c.candidate_id == enrollment.candidate_id))
            .values(active=enrollment.active))

    def for_exam(self, exam_id):
        return [self._of(r) for r in self._c.execute(
            select(t.enrollment).where(t.enrollment.c.exam_id == exam_id))]

    def for_candidate(self, candidate_id):
        return [self._of(r) for r in self._c.execute(
            select(t.enrollment).where(t.enrollment.c.candidate_id == candidate_id))]


class SqlAccounts(_Repo, AccountDirectory):
    """Reads identity rows. Provisioning needs the foundation's Argon2id hasher."""

    def __init__(self, conn: Connection, hasher: Callable[[str], str] | None,
                 ids: Callable[[], UUID]) -> None:
        super().__init__(conn)
        self._hash = hasher
        self._ids = ids

    def _records(self, statement) -> list[AccountRecord]:
        rows = self._c.execute(statement).all()
        roles: dict[UUID, set[str]] = defaultdict(set)
        if rows:
            for r in self._c.execute(select(t.account_role).where(
                    t.account_role.c.account_id.in_([r.id for r in rows]))):
                roles[r.account_id].add(r.role_name)
        return [AccountRecord(r.id, r.email, r.display_name, r.enabled, frozenset(roles[r.id]))
                for r in rows]

    def by_email(self, email):
        found = self._records(select(t.account).where(
            func.lower(func.trim(t.account.c.email)) == email.strip().lower()))
        return found[0] if found else None

    def by_ids(self, account_ids):
        ids = list(account_ids)
        if not ids:
            return {}
        return {r.id: r for r in self._records(select(t.account).where(t.account.c.id.in_(ids)))}

    def provision_candidate(self, email, display_name):
        if self._hash is None:
            raise NotImplementedError("Supply the identity service's password hasher.")
        credential = secrets.token_urlsafe(12)
        account_id = self._ids()
        self._c.execute(insert(t.account).values(
            id=account_id, email=email.strip(), display_name=display_name.strip(),
            password_hash=self._hash(credential), enabled=True))
        self._c.execute(insert(t.account_role).values(account_id=account_id,
                                                      role_name="candidate"))
        return ProvisionedCandidate(AccountRecord(account_id, email.strip(), display_name.strip(),
                                                  True, frozenset({"candidate"})), credential)


class SqlUnitOfWork(UnitOfWork):
    def __init__(self, database: "SqlDatabase") -> None:
        self._db = database

    def __enter__(self):
        self._conn = self._db.engine.connect()
        self._tx = self._conn.begin()
        self.exams = SqlExams(self._conn)
        self.questions = SqlQuestions(self._conn)
        self.enrollments = SqlEnrollments(self._conn)
        self.accounts = SqlAccounts(self._conn, self._db.hasher, self._db.ids)
        return self

    def __exit__(self, *exc):
        try:
            if self._tx.is_active:
                self._tx.rollback()
        finally:
            self._conn.close()

    def now(self) -> datetime:
        if self._db.clock:
            return self._db.clock()
        if self._conn.dialect.name == "postgresql":
            return self._conn.execute(select(func.clock_timestamp())).scalar_one()
        return datetime.now(timezone.utc)

    def commit(self):
        self._tx.commit()
        self._tx = self._conn.begin()

    def rollback(self):
        self._tx.rollback()
        self._tx = self._conn.begin()


class SqlDatabase:
    """Factory for SQL units of work.

    ``clock`` overrides database time for tests only; production leaves it unset.
    ``hasher`` is the identity service's password hasher for imported candidates.
    """

    def __init__(self, engine: Engine, *, hasher: Callable[[str], str] | None = None,
                 clock: Callable[[], datetime] | None = None,
                 ids: Callable[[], UUID] = uuid4) -> None:
        self.engine = engine
        self.hasher = hasher
        self.clock = clock
        self.ids = ids

    def unit_of_work(self) -> SqlUnitOfWork:
        return SqlUnitOfWork(self)
