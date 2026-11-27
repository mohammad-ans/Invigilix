"""SQLAlchemy Core unit-of-work and repositories for the results feature."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Iterable
from uuid import UUID

from sqlalchemy import Engine, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from ..domain import (
    AccountSummary,
    AnnouncementRecord,
    AttemptEventRecord,
    AttemptItemRecord,
    AttemptOptionRecord,
    AttemptRecord,
    EnrollmentRecord,
    ExamItemSpec,
    ExamRecord,
    OptionSpec,
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
from .sql_tables import (
    account,
    account_role,
    announcement,
    attempt,
    attempt_event,
    attempt_item,
    attempt_option,
    enrollment,
    exam,
    exam_item,
    question_option,
    question_version,
    result_report,
)


def _to_exam(row) -> ExamRecord:
    return ExamRecord(
        id=row.id,
        owner_id=row.owner_id,
        title=row.title,
        instructions=row.instructions,
        opens_at=row.opens_at,
        closes_at=row.closes_at,
        duration_seconds=row.duration_seconds,
        total_marks=quantize_marks(row.total_marks),
        shuffle_objective=bool(row.shuffle_objective),
        shuffle_choices=bool(row.shuffle_choices),
        published_at=row.published_at,
        results_published_at=row.results_published_at,
    )


def _to_attempt(row) -> AttemptRecord:
    return AttemptRecord(
        id=row.id,
        exam_id=row.exam_id,
        candidate_id=row.candidate_id,
        started_at=row.started_at,
        deadline_at=row.deadline_at,
        finalized_at=row.finalized_at,
        close_reason=row.close_reason,
    )


def _to_report(row) -> ResultReportRecord:
    return ResultReportRecord(
        verification_code=row.verification_code,
        attempt_id=row.attempt_id,
        issued_at=row.issued_at,
        sha256_hex=row.sha256_hex,
        pdf_bytes=bytes(row.pdf_bytes),
    )


class _SqlExamRepo(ExamReadWriteRepository):
    def __init__(self, session: Session, is_pg: bool) -> None:
        self._s = session
        self._is_pg = is_pg

    def get(self, exam_id: UUID, *, lock: bool = False) -> ExamRecord | None:
        stmt = select(exam).where(exam.c.id == exam_id)
        if lock and self._is_pg:
            stmt = stmt.with_for_update()
        row = self._s.execute(stmt).first()
        return _to_exam(row) if row is not None else None

    def paper_items(self, exam_id: UUID) -> list[ExamItemSpec]:
        stmt = (
            select(
                exam_item.c.exam_id,
                exam_item.c.slot,
                exam_item.c.version_id,
                exam_item.c.max_marks,
                question_version.c.question_id,
                question_version.c.version_no,
                question_version.c.topic,
                question_version.c.difficulty,
                question_version.c.prompt,
                question_version.c.kind,
                question_version.c.marking_rule,
                question_version.c.rubric,
            )
            .join(question_version, question_version.c.id == exam_item.c.version_id)
            .where(exam_item.c.exam_id == exam_id)
            .order_by(exam_item.c.slot)
        )
        rows = self._s.execute(stmt).all()
        if not rows:
            return []

        version_ids = [r.version_id for r in rows]
        opt_rows = self._s.execute(
            select(question_option)
            .where(question_option.c.version_id.in_(version_ids))
            .order_by(question_option.c.version_id, question_option.c.option_no)
        ).all()
        opts_by_ver: dict[UUID, list[OptionSpec]] = {}
        for opt in opt_rows:
            opts_by_ver.setdefault(opt.version_id, []).append(
                OptionSpec(
                    option_no=opt.option_no,
                    label=opt.label,
                    is_correct=bool(opt.is_correct),
                )
            )

        return [
            ExamItemSpec(
                exam_id=r.exam_id,
                slot=r.slot,
                version_id=r.version_id,
                question_id=r.question_id,
                version_no=r.version_no,
                topic=r.topic,
                difficulty=r.difficulty,
                prompt=r.prompt,
                kind=r.kind,
                marking_rule=r.marking_rule,
                rubric=r.rubric,
                max_marks=quantize_marks(r.max_marks),
                options=tuple(opts_by_ver.get(r.version_id, ())),
            )
            for r in rows
        ]

    def set_results_published(self, exam_id: UUID, published_at: datetime) -> ExamRecord:
        self._s.execute(
            update(exam).where(exam.c.id == exam_id).values(results_published_at=published_at)
        )
        updated = self.get(exam_id)
        assert updated is not None
        return updated


class _SqlEnrollmentRepo(EnrollmentReadRepository):
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, exam_id: UUID, candidate_id: UUID) -> EnrollmentRecord | None:
        row = self._s.execute(
            select(enrollment).where(
                enrollment.c.exam_id == exam_id,
                enrollment.c.candidate_id == candidate_id,
            )
        ).first()
        if row is None:
            return None
        return EnrollmentRecord(
            exam_id=row.exam_id,
            candidate_id=row.candidate_id,
            enrolled_by=row.enrolled_by,
            active=bool(row.active),
        )

    def for_exam(self, exam_id: UUID) -> list[EnrollmentRecord]:
        rows = self._s.execute(
            select(enrollment).where(enrollment.c.exam_id == exam_id)
        ).all()
        return [
            EnrollmentRecord(
                exam_id=r.exam_id,
                candidate_id=r.candidate_id,
                enrolled_by=r.enrolled_by,
                active=bool(r.active),
            )
            for r in rows
        ]


class _SqlAttemptRepo(AttemptResultsRepository):
    def __init__(self, session: Session, is_pg: bool) -> None:
        self._s = session
        self._is_pg = is_pg

    def get(self, attempt_id: UUID, *, lock: bool = False) -> AttemptRecord | None:
        stmt = select(attempt).where(attempt.c.id == attempt_id)
        if lock and self._is_pg:
            stmt = stmt.with_for_update()
        row = self._s.execute(stmt).first()
        return _to_attempt(row) if row is not None else None

    def for_exam(self, exam_id: UUID) -> list[AttemptRecord]:
        rows = self._s.execute(select(attempt).where(attempt.c.exam_id == exam_id)).all()
        return [_to_attempt(r) for r in rows]

    def _hydrate_items(self, item_rows) -> list[AttemptItemRecord]:
        if not item_rows:
            return []
        att_ids = {r.attempt_id for r in item_rows}
        opt_rows = self._s.execute(
            select(attempt_option)
            .where(attempt_option.c.attempt_id.in_(att_ids))
            .order_by(attempt_option.c.attempt_id, attempt_option.c.slot, attempt_option.c.display_no)
        ).all()
        opts_by_key: dict[tuple[UUID, int], list[AttemptOptionRecord]] = {}
        for o in opt_rows:
            opts_by_key.setdefault((o.attempt_id, o.slot), []).append(
                AttemptOptionRecord(
                    attempt_id=o.attempt_id,
                    slot=o.slot,
                    version_id=o.version_id,
                    option_no=o.option_no,
                    display_no=o.display_no,
                    selected=bool(o.selected),
                )
            )
        return [
            AttemptItemRecord(
                attempt_id=r.attempt_id,
                exam_id=r.exam_id,
                slot=r.slot,
                version_id=r.version_id,
                display_no=r.display_no,
                written_answer=r.written_answer,
                flagged=bool(r.flagged),
                answer_revision=r.answer_revision,
                saved_at=r.saved_at,
                awarded_marks=quantize_marks(r.awarded_marks) if r.awarded_marks is not None else None,
                graded_by=r.graded_by,
                options=tuple(opts_by_key.get((r.attempt_id, r.slot), ())),
            )
            for r in item_rows
        ]

    def items_for_attempt(self, attempt_id: UUID) -> list[AttemptItemRecord]:
        rows = self._s.execute(
            select(attempt_item)
            .where(attempt_item.c.attempt_id == attempt_id)
            .order_by(attempt_item.c.slot)
        ).all()
        return self._hydrate_items(rows)

    def items_for_exam(self, exam_id: UUID) -> dict[UUID, list[AttemptItemRecord]]:
        rows = self._s.execute(
            select(attempt_item)
            .where(attempt_item.c.exam_id == exam_id)
            .order_by(attempt_item.c.attempt_id, attempt_item.c.slot)
        ).all()
        grouped: dict[UUID, list[AttemptItemRecord]] = {}
        for item in self._hydrate_items(rows):
            grouped.setdefault(item.attempt_id, []).append(item)
        return grouped

    def set_item_award(
        self,
        attempt_id: UUID,
        slot: int,
        awarded_marks: Decimal,
        graded_by: UUID,
    ) -> AttemptItemRecord:
        self._s.execute(
            update(attempt_item)
            .where(attempt_item.c.attempt_id == attempt_id, attempt_item.c.slot == slot)
            .values(awarded_marks=awarded_marks, graded_by=graded_by)
        )
        rows = self._s.execute(
            select(attempt_item).where(
                attempt_item.c.attempt_id == attempt_id,
                attempt_item.c.slot == slot,
            )
        ).all()
        hydrated = self._hydrate_items(rows)
        assert len(hydrated) == 1
        return hydrated[0]

    def events_for_exam(self, exam_id: UUID) -> list[AttemptEventRecord]:
        rows = self._s.execute(
            select(attempt_event)
            .join(attempt, attempt.c.id == attempt_event.c.attempt_id)
            .where(attempt.c.exam_id == exam_id)
            .order_by(attempt_event.c.recorded_at)
        ).all()
        return [
            AttemptEventRecord(
                id=r.id,
                attempt_id=r.attempt_id,
                kind=r.kind,
                recorded_at=r.recorded_at,
                note=r.note,
            )
            for r in rows
        ]


class _SqlAnnouncementRepo(AnnouncementRepository):
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_exam(self, exam_id: UUID) -> list[AnnouncementRecord]:
        rows = self._s.execute(
            select(announcement)
            .where(announcement.c.exam_id == exam_id)
            .order_by(announcement.c.posted_at)
        ).all()
        return [
            AnnouncementRecord(
                id=r.id,
                exam_id=r.exam_id,
                author_id=r.author_id,
                posted_at=r.posted_at,
                message=r.message,
            )
            for r in rows
        ]

    def add(self, ann: AnnouncementRecord) -> None:
        self._s.execute(
            announcement.insert().values(
                id=ann.id,
                exam_id=ann.exam_id,
                author_id=ann.author_id,
                posted_at=ann.posted_at,
                message=ann.message,
            )
        )


class _SqlReportRepo(ReportRepository):
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_attempt(self, attempt_id: UUID) -> ResultReportRecord | None:
        row = self._s.execute(
            select(result_report).where(result_report.c.attempt_id == attempt_id)
        ).first()
        return _to_report(row) if row is not None else None

    def get_by_code(self, verification_code: str) -> ResultReportRecord | None:
        row = self._s.execute(
            select(result_report).where(result_report.c.verification_code == verification_code)
        ).first()
        return _to_report(row) if row is not None else None

    def for_exam(self, exam_id: UUID) -> dict[UUID, ResultReportRecord]:
        rows = self._s.execute(
            select(result_report)
            .join(attempt, attempt.c.id == result_report.c.attempt_id)
            .where(attempt.c.exam_id == exam_id)
        ).all()
        return {r.attempt_id: _to_report(r) for r in rows}

    def add(self, report: ResultReportRecord) -> None:
        self._s.execute(
            result_report.insert().values(
                verification_code=report.verification_code,
                attempt_id=report.attempt_id,
                issued_at=report.issued_at,
                sha256_hex=report.sha256_hex,
                pdf_bytes=report.pdf_bytes,
            )
        )


class _SqlAccountLookup(AccountLookup):
    def __init__(self, session: Session) -> None:
        self._s = session

    def by_ids(self, account_ids: Iterable[UUID]) -> dict[UUID, AccountSummary]:
        ids = list(set(account_ids))
        if not ids:
            return {}
        acct_rows = self._s.execute(select(account).where(account.c.id.in_(ids))).all()
        role_rows = self._s.execute(
            select(account_role).where(account_role.c.account_id.in_(ids))
        ).all()
        roles_by_id: dict[UUID, set[str]] = {}
        for r in role_rows:
            roles_by_id.setdefault(r.account_id, set()).add(r.role_name)
        return {
            r.id: AccountSummary(
                id=r.id,
                email=r.email,
                display_name=r.display_name,
                roles=frozenset(roles_by_id.get(r.id, ())),
                enabled=bool(r.enabled),
            )
            for r in acct_rows
        }


class SqlResultsUnitOfWork(ResultsUnitOfWork):
    """SQLAlchemy-backed unit of work over contracts/exam_schema.sql."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> "SqlResultsUnitOfWork":
        self._session = self._session_factory()
        is_pg = self._session.bind is not None and self._session.bind.dialect.name == "postgresql"
        self.exams = _SqlExamRepo(self._session, is_pg)
        self.enrollments = _SqlEnrollmentRepo(self._session)
        self.attempts = _SqlAttemptRepo(self._session, is_pg)
        self.announcements = _SqlAnnouncementRepo(self._session)
        self.reports = _SqlReportRepo(self._session)
        self.accounts = _SqlAccountLookup(self._session)
        return self

    def now(self) -> datetime:
        if self._clock is not None:
            return self._clock().astimezone(timezone.utc)
        assert self._session is not None
        if self._session.bind is not None and self._session.bind.dialect.name == "postgresql":
            ts = self._session.execute(text("SELECT clock_timestamp()")).scalar_one()
            return ts.astimezone(timezone.utc) if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc)

    def commit(self) -> None:
        assert self._session is not None
        self._session.commit()
        self._committed = True

    def rollback(self) -> None:
        if self._session is not None and not self._committed:
            self._session.rollback()

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is not None or not self._committed:
                self.rollback()
        finally:
            if self._session is not None:
                self._session.close()
                self._session = None


def sql_uow_factory(
    engine: Engine,
    *,
    clock: Callable[[], datetime] | None = None,
) -> Callable[[], SqlResultsUnitOfWork]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return lambda: SqlResultsUnitOfWork(factory, clock=clock)
