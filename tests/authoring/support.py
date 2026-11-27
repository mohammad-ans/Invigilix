"""A fictional world for service and API tests: one admin, two examiners, two
candidates and a controllable server clock. ``Backend`` implementations let the
same scenarios run against the in-memory and SQLAlchemy adapters."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable
from uuid import UUID, uuid4

from app.features.authoring.domain import (
    AccountRecord, AnswerOption, Difficulty, ExamDetails, MarkingRule, QuestionContent,
    QuestionKind,
)
from app.features.authoring.ports import Actor, UnitOfWork
from app.features.authoring.services import AuthoringModule, SlotRequest

UTC = timezone.utc
OPENS = datetime(2026, 11, 27, 10, 30, tzinfo=UTC)
CLOSES = datetime(2026, 11, 27, 11, 0, tzinfo=UTC)
BEFORE = OPENS - timedelta(hours=2)


@dataclass
class Clock:
    current: datetime = BEFORE

    def __call__(self) -> datetime:
        return self.current


@dataclass
class World:
    module: AuthoringModule
    clock: Clock
    snapshot: Callable[[], object]
    accounts: dict[str, AccountRecord] = field(default_factory=dict)

    def actor(self, name: str) -> Actor:
        record = self.accounts[name]
        return Actor(record.id, record.roles)

    # -- builders --------------------------------------------------------------
    def details(self, total: str = "10", **overrides) -> ExamDetails:
        values = dict(title="Field ecology", instructions="Answer every question.",
                      opens_at=OPENS, closes_at=CLOSES, duration_minutes=30, total_marks=total,
                      shuffle_questions=True, shuffle_choices=True)
        values.update(overrides)
        return ExamDetails.build(**values)

    def question(self, owner: str = "examiner", prompt: str = "Which factor is abiotic?",
                 kind: QuestionKind = QuestionKind.SINGLE):
        return self.module.bank.create(self.actor(owner), content(prompt, kind))

    def three_item_paper(self, owner: str = "examiner", total: str = "10"):
        """The AT02 paper: bank items worth 2, 4 and 4."""
        actor = self.actor(owner)
        exam = self.module.exams.create_draft(actor, self.details(total)).exam
        q1 = self.question(owner, "Which factor is abiotic?")
        q2 = self.question(owner, "Which measurements describe diversity?", QuestionKind.MULTIPLE)
        q3 = self.question(owner, "Why repeat the survey on a second transect?",
                           QuestionKind.WRITTEN)
        self.module.exams.assign(actor, exam.id, [SlotRequest(q1.id, "2"), SlotRequest(q2.id, "4"),
                                                  SlotRequest(q3.id, "4")])
        return exam.id, (q1, q2, q3)


def content(prompt: str = "Which factor is abiotic?",
            kind: QuestionKind = QuestionKind.SINGLE, keys: tuple[int, ...] | None = None,
            topic: str = "Ecology", difficulty: Difficulty = Difficulty.MEDIUM) -> QuestionContent:
    if kind is QuestionKind.WRITTEN:
        return QuestionContent(topic, difficulty, kind, prompt, MarkingRule.MANUAL, (),
                               "Mentions replication and representativeness.")
    rule = MarkingRule.EXACT if kind is QuestionKind.SINGLE else MarkingRule.PARTIAL_NO_WRONG
    keys = keys if keys is not None else ((1,) if kind is QuestionKind.SINGLE else (1, 3))
    labels = ["Light intensity", "Rabbit population", "Soil moisture"]
    return QuestionContent(topic, difficulty, kind, prompt, rule,
                           tuple(AnswerOption(i, label, i in keys)
                                 for i, label in enumerate(labels, start=1)))


def populate(add_account: Callable[..., AccountRecord], world: World) -> None:
    world.accounts.update(
        admin=add_account("ada@example.test", "Ada Admin", "admin"),
        examiner=add_account("remy@example.test", "Remy Chen", "examiner"),
        other=add_account("ola@example.test", "Ola Examiner", "examiner"),
        nora=add_account("nora@example.test", "Nora Khan", "candidate"),
        eli=add_account("eli@example.test", "Eli Brooks", "candidate"),
        disabled=add_account("dee@example.test", "Dee Disabled", "candidate", enabled=False),
    )


def memory_world() -> World:
    from app.features.authoring.adapters.memory import MemoryDatabase

    clock = Clock()
    db = MemoryDatabase(clock)
    world = World(AuthoringModule(db.unit_of_work), clock,
                  lambda: repr(sorted((k, repr(v)) for k, v in vars(db.store).items())))
    populate(db.store.add_account, world)
    return world


def sql_world() -> World:
    """SQLite in memory through the SQLAlchemy adapter, using the contract tables."""
    from sqlalchemy import create_engine, insert, select
    from sqlalchemy.pool import StaticPool

    from app.features.authoring.adapters import sql_tables as t
    from app.features.authoring.adapters.sql import SqlDatabase

    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    t.metadata.create_all(engine)
    clock = Clock()
    db = SqlDatabase(engine, hasher=lambda secret: "test-hash:" + secret[::-1], clock=clock)
    world = World(AuthoringModule(db.unit_of_work), clock, lambda: _dump(engine, t, select))

    def add_account(email, display_name, *roles, enabled=True):
        record = AccountRecord(uuid4(), email, display_name, enabled, frozenset(roles))
        with engine.begin() as conn:
            conn.execute(insert(t.account).values(id=record.id, email=email,
                                                  display_name=display_name,
                                                  password_hash="x", enabled=enabled))
            for role in roles:
                conn.execute(insert(t.account_role).values(account_id=record.id, role_name=role))
        return record

    populate(add_account, world)
    return world


def _dump(engine, tables, select) -> list:
    with engine.connect() as conn:
        return [(table.name, sorted(map(repr, conn.execute(select(table)).all())))
                for table in tables.metadata.sorted_tables]


def marks(value: str) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


__all__ = ["BEFORE", "CLOSES", "OPENS", "SlotRequest", "UUID", "UnitOfWork", "World", "content",
           "marks", "memory_world", "populate"]
