"""Live examination monitoring and examiner announcements (FR10, AT06)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping
from uuid import UUID, uuid4

from ..domain import (
    AccountSummary,
    AnnouncementRecord,
    AttemptEventRecord,
    AttemptItemRecord,
    AttemptRecord,
    Conflict,
    ExamStatus,
    Forbidden,
    Issue,
    NotFound,
    ValidationFailed,
    derive_exam_status,
    is_item_blank,
)
from ..ports import Actor, CANDIDATE, EXAMINER
from .base import UowFactory, load_owned_exam, require_enabled

MAX_ANNOUNCEMENT_LEN = 2000


@dataclass(frozen=True)
class MonitorCounts:
    enrolled: int
    not_started: int
    in_progress: int
    submitted: int
    expired: int
    finalized: int

    @classmethod
    def of(cls, rows: "tuple[RosterProgressRow, ...]", enrolled: int) -> "MonitorCounts":
        """Derive the counts from the roster rows, so they can never disagree."""
        status = [r.status for r in rows]
        submitted, expired = status.count("submitted"), status.count("expired")
        return cls(enrolled=enrolled, not_started=status.count("not_started"),
                   in_progress=status.count("working") + status.count("reconnected"),
                   submitted=submitted, expired=expired, finalized=submitted + expired)


@dataclass(frozen=True)
class RosterProgressRow:
    candidate_id: UUID
    display_name: str
    email: str
    enrollment_active: bool
    attempt_id: UUID | None
    status: str
    answered_count: int
    total_items: int
    started_at: datetime | None
    deadline_at: datetime | None
    finalized_at: datetime | None
    close_reason: str | None
    last_saved_at: datetime | None
    incident_count: int


@dataclass(frozen=True)
class IncidentEventView:
    id: UUID
    attempt_id: UUID
    candidate_id: UUID
    candidate_name: str
    kind: str
    recorded_at: datetime
    note: str | None


@dataclass(frozen=True)
class AnnouncementView:
    id: UUID
    exam_id: UUID
    author_id: UUID
    author_name: str
    posted_at: datetime
    message: str

    @classmethod
    def of(cls, record: AnnouncementRecord, accounts: Mapping[UUID, AccountSummary]) -> "AnnouncementView":
        author = accounts.get(record.author_id)
        return cls(id=record.id, exam_id=record.exam_id, author_id=record.author_id,
                   author_name=author.display_name if author else "Examiner",
                   posted_at=record.posted_at, message=record.message)


@dataclass(frozen=True)
class MonitorSnapshot:
    exam_id: UUID
    exam_title: str
    status: ExamStatus
    opens_at: datetime
    closes_at: datetime
    published_at: datetime | None
    results_published_at: datetime | None
    server_time: datetime
    total_items: int
    counts: MonitorCounts
    roster: tuple[RosterProgressRow, ...]
    incidents: tuple[IncidentEventView, ...]
    announcements: tuple[AnnouncementView, ...]


class MonitorService:
    """Provides real-time scoped progress, incident observations, and announcements."""

    def __init__(self, uow_factory: UowFactory) -> None:
        self._uow = uow_factory

    def get_monitor(self, actor: Actor, exam_id: UUID) -> MonitorSnapshot:
        with self._uow() as uow:
            exam = load_owned_exam(uow, actor, exam_id)
            now = uow.now()
            paper = uow.exams.paper_items(exam.id)
            kind_by_slot = {spec.slot: spec.kind for spec in paper}
            total_items = len(paper)

            enrollments = uow.enrollments.for_exam(exam.id)
            attempts = uow.attempts.for_exam(exam.id)
            items_by_attempt = uow.attempts.items_for_exam(exam.id)
            events = uow.attempts.events_for_exam(exam.id)
            announcements = uow.announcements.for_exam(exam.id)

            account_ids = (
                {e.candidate_id for e in enrollments}
                | {a.candidate_id for a in attempts}
                | {ann.author_id for ann in announcements}
            )
            accounts = uow.accounts.by_ids(account_ids)

            attempt_by_candidate = {a.candidate_id: a for a in attempts}
            events_by_attempt: dict[UUID, list[AttemptEventRecord]] = {}
            for ev in events:
                events_by_attempt.setdefault(ev.attempt_id, []).append(ev)
            active_set = {e.candidate_id for e in enrollments if e.active}
            roster_ids = sorted(
                active_set | {a.candidate_id for a in attempts},
                key=lambda cid: accounts[cid].display_name.lower() if cid in accounts else str(cid),
            )
            roster = tuple(
                self._progress_row(cid, accounts.get(cid), attempt_by_candidate.get(cid),
                                   items_by_attempt, events_by_attempt, kind_by_slot,
                                   total_items, cid in active_set)
                for cid in roster_ids
            )
            attempt_owner = {a.id: a.candidate_id for a in attempts}
            return MonitorSnapshot(
                exam_id=exam.id,
                exam_title=exam.title,
                status=derive_exam_status(exam, now),
                opens_at=exam.opens_at,
                closes_at=exam.closes_at,
                published_at=exam.published_at,
                results_published_at=exam.results_published_at,
                server_time=now,
                total_items=total_items,
                counts=MonitorCounts.of(roster, enrolled=len(active_set)),
                roster=roster,
                incidents=tuple(self._incident_view(ev, attempt_owner, accounts)
                                for ev in sorted(events, key=lambda e: e.recorded_at, reverse=True)),
                announcements=tuple(AnnouncementView.of(a, accounts)
                                    for a in sorted(announcements, key=lambda a: a.posted_at, reverse=True)),
            )

    @staticmethod
    def _progress_row(candidate_id: UUID, account: AccountSummary | None,
                      attempt: AttemptRecord | None,
                      items_by_attempt: Mapping[UUID, list[AttemptItemRecord]],
                      events_by_attempt: Mapping[UUID, list[AttemptEventRecord]],
                      kind_by_slot: Mapping[int, str], total_items: int,
                      active: bool) -> RosterProgressRow:
        """One candidate's progress: answered count, latest save, observations, status."""
        name = account.display_name if account else str(candidate_id)
        email = account.email if account else ""
        if attempt is None:
            return RosterProgressRow(candidate_id, name, email, active, None, "not_started", 0,
                                     total_items, None, None, None, None, None, 0)
        items = items_by_attempt.get(attempt.id, ())
        answered = sum(1 for it in items
                       if it.slot in kind_by_slot and not is_item_blank(it, kind_by_slot[it.slot]))
        saved = [it.saved_at for it in items if it.saved_at is not None]
        timeline = sorted(events_by_attempt.get(attempt.id, ()), key=lambda ev: ev.recorded_at)
        observations = sum(1 for ev in timeline if ev.kind in ("reconnected", "reported_incident"))
        if attempt.finalized_at is not None:
            status = attempt.close_reason or "submitted"
        else:
            status = "reconnected" if timeline and timeline[-1].kind == "reconnected" else "working"
        return RosterProgressRow(candidate_id, name, email, active, attempt.id, status, answered,
                                 total_items, attempt.started_at, attempt.deadline_at,
                                 attempt.finalized_at, attempt.close_reason,
                                 max(saved) if saved else None, observations)

    @staticmethod
    def _incident_view(ev: AttemptEventRecord, attempt_owner: Mapping[UUID, UUID],
                       accounts: Mapping[UUID, AccountSummary]) -> IncidentEventView:
        candidate_id = attempt_owner.get(ev.attempt_id)
        account = accounts.get(candidate_id) if candidate_id else None
        return IncidentEventView(id=ev.id, attempt_id=ev.attempt_id, candidate_id=candidate_id,
                                 candidate_name=account.display_name if account else str(candidate_id or ""),
                                 kind=ev.kind, recorded_at=ev.recorded_at, note=ev.note)

    def post_announcement(self, actor: Actor, exam_id: UUID, message: str) -> AnnouncementView:
        cleaned = message.strip()
        if not cleaned:
            raise ValidationFailed(
                [Issue("empty_message", "Announcement message cannot be blank.", field="message")]
            )
        if len(cleaned) > MAX_ANNOUNCEMENT_LEN:
            raise ValidationFailed(
                [
                    Issue(
                        "message_too_long",
                        f"Announcement must be at most {MAX_ANNOUNCEMENT_LEN} characters.",
                        field="message",
                    )
                ]
            )

        with self._uow() as uow:
            exam = load_owned_exam(uow, actor, exam_id, lock=True)
            now = uow.now()
            if exam.published_at is None:
                raise Conflict("exam_not_published", "Publish the exam before posting announcements.")
            if now >= exam.closes_at:
                raise Conflict("exam_closed", "Announcements cannot be posted after the exam closes.")

            record = AnnouncementRecord(
                id=uuid4(),
                exam_id=exam.id,
                author_id=actor.id,
                posted_at=now,
                message=cleaned,
            )
            uow.announcements.add(record)
            accounts = uow.accounts.by_ids([actor.id])
            uow.commit()
            return AnnouncementView.of(record, accounts)

    def list_announcements(self, actor: Actor, exam_id: UUID) -> list[AnnouncementView]:
        require_enabled(actor)
        if not (actor.has(EXAMINER) or actor.has(CANDIDATE)):
            raise Forbidden("Examiner or candidate role is required to view exam announcements.")

        with self._uow() as uow:
            exam = uow.exams.get(exam_id)
            if exam is None:
                raise NotFound("Exam")

            is_owner = actor.has(EXAMINER) and exam.owner_id == actor.id
            if not is_owner:
                if not actor.has(CANDIDATE) or exam.published_at is None:
                    raise NotFound("Exam")
                enrollment = uow.enrollments.get(exam.id, actor.id)
                if enrollment is None or not enrollment.active:
                    raise NotFound("Exam")

            announcements = uow.announcements.for_exam(exam.id)
            accounts = uow.accounts.by_ids({ann.author_id for ann in announcements})
            return [AnnouncementView.of(ann, accounts)
                    for ann in sorted(announcements, key=lambda a: a.posted_at, reverse=True)]
