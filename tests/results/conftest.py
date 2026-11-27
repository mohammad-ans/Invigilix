"""Shared fixtures and dual-backend seed builder (InMemory + SQLAlchemy) for results tests."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
from typing import Callable, Iterable
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.features.results import (
    ADMIN,
    Actor,
    CANDIDATE,
    EXAMINER,
    InMemoryResultsStore,
    ReportLabPdfRenderer,
    ResultsModule,
    metadata,
    score_finalized_item,
    sql_uow_factory,
)
from backend.app.features.results.adapters.sql_tables import (
    account as t_account,
    account_role as t_account_role,
    announcement as t_announcement,
    attempt as t_attempt,
    attempt_event as t_attempt_event,
    attempt_item as t_attempt_item,
    attempt_option as t_attempt_option,
    enrollment as t_enrollment,
    exam as t_exam,
    exam_item as t_exam_item,
    question as t_question,
    question_option as t_question_option,
    question_version as t_question_version,
)
from backend.app.features.results.domain import (
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
    quantize_marks,
)


class MutableClock:
    def __init__(self, initial: datetime) -> None:
        self.current = initial

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs) -> datetime:
        self.current = self.current + timedelta(**kwargs)
        return self.current

    def set(self, dt: datetime) -> None:
        self.current = dt


class DualBackendHarness:
    """Seeds identical test fixtures into either InMemoryResultsStore or SQLite/SQLAlchemy."""

    def __init__(self, backend_kind: str) -> None:
        self.kind = backend_kind
        self.clock = MutableClock(datetime(2026, 11, 27, 10, 45, tzinfo=timezone.utc))
        self.pdf = ReportLabPdfRenderer()

        if backend_kind == "memory":
            self.store = InMemoryResultsStore(clock=self.clock)
            self.uow_factory = self.store.uow
            self.engine = None
        else:
            self.store = None
            self.engine = create_engine(
                "sqlite://",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )

            @sa_event.listens_for(self.engine, "connect")
            def _enable_fk(dbapi_conn, _rec):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()

            metadata.create_all(self.engine)
            self.uow_factory = sql_uow_factory(self.engine, clock=self.clock)

        self.module = ResultsModule(self.uow_factory, self.pdf)

    def add_account(
        self,
        *,
        email: str,
        display_name: str,
        roles: Iterable[str] | frozenset[str],
        enabled: bool = True,
        account_id: UUID | None = None,
    ) -> Actor:
        aid = account_id or uuid4()
        role_set = frozenset(roles)
        summary = AccountSummary(
            id=aid,
            email=email,
            display_name=display_name,
            roles=role_set,
            enabled=enabled,
        )
        if self.store is not None:
            self.store.accounts[aid] = summary
        else:
            assert self.engine is not None
            with self.engine.begin() as conn:
                conn.execute(
                    t_account.insert().values(
                        id=aid,
                        email=email,
                        display_name=display_name,
                        password_hash="argon2id$test",
                        enabled=enabled,
                        font_percent=100,
                        workspace_layout="standard",
                    )
                )
                for r in role_set:
                    conn.execute(t_account_role.insert().values(account_id=aid, role_name=r))
        return Actor(id=aid, roles=role_set, enabled=enabled)

    def add_question_version(
        self,
        *,
        owner_id: UUID,
        topic: str,
        difficulty: str,
        prompt: str,
        kind: str,
        marking_rule: str,
        options: list[tuple[int, str, bool]] = (),
        rubric: str | None = None,
        question_id: UUID | None = None,
        version_id: UUID | None = None,
        version_no: int = 1,
    ) -> tuple[UUID, UUID, tuple[OptionSpec, ...]]:
        qid = question_id or uuid4()
        vid = version_id or uuid4()
        opt_specs = tuple(OptionSpec(no, label, corr) for no, label, corr in options)
        if self.engine is not None:
            with self.engine.begin() as conn:
                existing_q = conn.execute(
                    t_question.select().where(t_question.c.id == qid)
                ).first()
                if existing_q is None:
                    conn.execute(t_question.insert().values(id=qid, owner_id=owner_id))
                conn.execute(
                    t_question_version.insert().values(
                        id=vid,
                        question_id=qid,
                        version_no=version_no,
                        topic=topic,
                        difficulty=difficulty,
                        prompt=prompt,
                        kind=kind,
                        marking_rule=marking_rule,
                        rubric=rubric,
                    )
                )
                for opt in opt_specs:
                    conn.execute(
                        t_question_option.insert().values(
                            version_id=vid,
                            option_no=opt.option_no,
                            label=opt.label,
                            is_correct=opt.is_correct,
                        )
                    )
        return qid, vid, opt_specs

    def create_exam(
        self,
        *,
        owner_id: UUID,
        title: str = "Field ecology",
        instructions: str = "Answer all items carefully.",
        opens_at: datetime | None = None,
        closes_at: datetime | None = None,
        duration_seconds: int = 1800,
        total_marks: Decimal | str = "10.00",
        published_at: datetime | None = None,
        results_published_at: datetime | None = None,
        items: list[dict] = (),
        exam_id: UUID | None = None,
    ) -> ExamRecord:
        eid = exam_id or uuid4()
        opens = opens_at or datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc)
        closes = closes_at or datetime(2026, 11, 27, 11, 0, tzinfo=timezone.utc)
        pub = published_at
        record = ExamRecord(
            id=eid,
            owner_id=owner_id,
            title=title,
            instructions=instructions,
            opens_at=opens,
            closes_at=closes,
            duration_seconds=duration_seconds,
            total_marks=quantize_marks(total_marks),
            shuffle_objective=False,
            shuffle_choices=False,
            published_at=pub,
            results_published_at=results_published_at,
        )
        specs: list[ExamItemSpec] = []
        for idx, item in enumerate(items, start=1):
            qid, vid, opts = self.add_question_version(
                owner_id=owner_id,
                topic=item.get("topic", "Ecology"),
                difficulty=item.get("difficulty", "medium"),
                prompt=item["prompt"],
                kind=item["kind"],
                marking_rule=item["marking_rule"],
                options=item.get("options", ()),
                rubric=item.get("rubric"),
            )
            specs.append(
                ExamItemSpec(
                    exam_id=eid,
                    slot=idx,
                    version_id=vid,
                    question_id=qid,
                    version_no=1,
                    topic=item.get("topic", "Ecology"),
                    difficulty=item.get("difficulty", "medium"),
                    prompt=item["prompt"],
                    kind=item["kind"],
                    marking_rule=item["marking_rule"],
                    rubric=item.get("rubric"),
                    max_marks=quantize_marks(item["max_marks"]),
                    options=opts,
                )
            )
        if self.store is not None:
            self.store.exams[eid] = record
            self.store.paper_items[eid] = specs
        else:
            assert self.engine is not None
            with self.engine.begin() as conn:
                conn.execute(
                    t_exam.insert().values(
                        id=eid,
                        owner_id=owner_id,
                        title=title,
                        instructions=instructions,
                        opens_at=opens,
                        closes_at=closes,
                        duration_seconds=duration_seconds,
                        total_marks=record.total_marks,
                        shuffle_objective=False,
                        shuffle_choices=False,
                        published_at=pub,
                        results_published_at=results_published_at,
                    )
                )
                for spec in specs:
                    conn.execute(
                        t_exam_item.insert().values(
                            exam_id=eid,
                            slot=spec.slot,
                            version_id=spec.version_id,
                            max_marks=spec.max_marks,
                        )
                    )
        return record

    def enroll(
        self,
        *,
        exam_id: UUID,
        candidate_id: UUID,
        enrolled_by: UUID,
        active: bool = True,
    ) -> EnrollmentRecord:
        rec = EnrollmentRecord(
            exam_id=exam_id,
            candidate_id=candidate_id,
            enrolled_by=enrolled_by,
            active=active,
        )
        if self.store is not None:
            self.store.enrollments[(exam_id, candidate_id)] = rec
        else:
            assert self.engine is not None
            with self.engine.begin() as conn:
                conn.execute(
                    t_enrollment.insert().values(
                        exam_id=exam_id,
                        candidate_id=candidate_id,
                        enrolled_by=enrolled_by,
                        active=active,
                    )
                )
        return rec

    def create_attempt(
        self,
        *,
        exam: ExamRecord,
        candidate_id: UUID,
        started_at: datetime | None = None,
        deadline_at: datetime | None = None,
        finalized_at: datetime | None = None,
        close_reason: str | None = None,
        responses: dict[int, dict] | None = None,
        events: list[tuple[str, datetime, str | None]] = (),
        auto_score_on_finalize: bool = True,
    ) -> AttemptRecord:
        aid = uuid4()
        start = started_at or (exam.opens_at + timedelta(minutes=2))
        deadline = deadline_at or min(start + timedelta(seconds=exam.duration_seconds), exam.closes_at)
        att = AttemptRecord(
            id=aid,
            exam_id=exam.id,
            candidate_id=candidate_id,
            started_at=start,
            deadline_at=deadline,
            finalized_at=finalized_at,
            close_reason=close_reason,
        )

        with self.uow_factory() as uow:
            paper = uow.exams.paper_items(exam.id)

        responses = responses or {}
        att_items: list[AttemptItemRecord] = []
        for idx, spec in enumerate(paper, start=1):
            resp = responses.get(spec.slot, {})
            selected_set = set(resp.get("selected", ()))
            written_text = resp.get("written", "")
            flagged = bool(resp.get("flagged", False))
            saved_at = resp.get("saved_at")
            rev = int(resp.get("revision", 1 if (selected_set or written_text) else 0))

            opt_recs = tuple(
                AttemptOptionRecord(
                    attempt_id=aid,
                    slot=spec.slot,
                    version_id=spec.version_id,
                    option_no=opt.option_no,
                    display_no=opt.option_no,
                    selected=opt.option_no in selected_set,
                )
                for opt in spec.options
            )

            award = resp.get("awarded_marks")
            if award is None and finalized_at is not None and auto_score_on_finalize:
                award = score_finalized_item(
                    spec.kind,
                    spec.marking_rule,
                    spec.max_marks,
                    selected_ids=selected_set,
                    correct_ids={o.option_no for o in spec.options if o.is_correct},
                    written_answer=written_text,
                )

            att_items.append(
                AttemptItemRecord(
                    attempt_id=aid,
                    exam_id=exam.id,
                    slot=spec.slot,
                    version_id=spec.version_id,
                    display_no=resp.get("display_no", idx),
                    written_answer=written_text,
                    flagged=flagged,
                    answer_revision=rev,
                    saved_at=saved_at,
                    awarded_marks=quantize_marks(award) if award is not None else None,
                    graded_by=resp.get("graded_by"),
                    options=opt_recs,
                )
            )

        event_recs = [
            AttemptEventRecord(
                id=uuid4(),
                attempt_id=aid,
                kind=kind,
                recorded_at=ts,
                note=note,
            )
            for kind, ts, note in events
        ]

        if self.store is not None:
            self.store.attempts[aid] = att
            self.store.attempt_items[aid] = att_items
            self.store.attempt_events.extend(event_recs)
        else:
            assert self.engine is not None
            with self.engine.begin() as conn:
                conn.execute(
                    t_attempt.insert().values(
                        id=aid,
                        exam_id=exam.id,
                        candidate_id=candidate_id,
                        started_at=start,
                        deadline_at=deadline,
                        finalized_at=finalized_at,
                        close_reason=close_reason,
                    )
                )
                for it in att_items:
                    conn.execute(
                        t_attempt_item.insert().values(
                            attempt_id=aid,
                            exam_id=exam.id,
                            slot=it.slot,
                            version_id=it.version_id,
                            display_no=it.display_no,
                            written_answer=it.written_answer,
                            flagged=it.flagged,
                            answer_revision=it.answer_revision,
                            saved_at=it.saved_at,
                            awarded_marks=it.awarded_marks,
                            graded_by=it.graded_by,
                        )
                    )
                    for opt in it.options:
                        conn.execute(
                            t_attempt_option.insert().values(
                                attempt_id=aid,
                                slot=opt.slot,
                                version_id=opt.version_id,
                                option_no=opt.option_no,
                                display_no=opt.display_no,
                                selected=opt.selected,
                            )
                        )
                for ev in event_recs:
                    conn.execute(
                        t_attempt_event.insert().values(
                            id=ev.id,
                            attempt_id=ev.attempt_id,
                            kind=ev.kind,
                            recorded_at=ev.recorded_at,
                            note=ev.note,
                        )
                    )
        return att


@pytest.fixture(params=["memory", "sql"])
def harness(request) -> DualBackendHarness:
    return DualBackendHarness(request.param)
