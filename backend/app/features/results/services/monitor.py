"""Live examination monitoring and examiner announcements (FR10, AT06)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from ..domain import (
    AnnouncementRecord,
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
            events_by_attempt: dict[UUID, list] = {}
            for ev in events:
                events_by_attempt.setdefault(ev.attempt_id, []).append(ev)

            roster_ids = sorted(
                {e.candidate_id for e in enrollments if e.active} | {a.candidate_id for a in attempts},
                key=lambda cid: accounts.get(cid).display_name.lower() if cid in accounts else str(cid),
            )
            active_set = {e.candidate_id for e in enrollments if e.active}

            roster: list[RosterProgressRow] = []
            not_started = in_progress = submitted = expired = 0

            for cid in roster_ids:
                acct = accounts.get(cid)
                display_name = acct.display_name if acct else str(cid)
                email = acct.email if acct else ""
                att = attempt_by_candidate.get(cid)
                if att is None:
                    not_started += 1
                    roster.append(
                        RosterProgressRow(
                            candidate_id=cid,
                            display_name=display_name,
                            email=email,
                            enrollment_active=cid in active_set,
                            attempt_id=None,
                            status="not_started",
                            answered_count=0,
                            total_items=total_items,
                            started_at=None,
                            deadline_at=None,
                            finalized_at=None,
                            close_reason=None,
                            last_saved_at=None,
                            incident_count=0,
                        )
                    )
                    continue

                att_items = items_by_attempt.get(att.id, ())
                answered = sum(
                    1
                    for it in att_items
                    if it.slot in kind_by_slot and not is_item_blank(it, kind_by_slot[it.slot])
                )
                saved_times = [it.saved_at for it in att_items if it.saved_at is not None]
                last_saved = max(saved_times) if saved_times else None
                att_events = sorted(
                    events_by_attempt.get(att.id, ()),
                    key=lambda ev: ev.recorded_at,
                )
                incident_count = sum(
                    1 for ev in att_events if ev.kind in ("reconnected", "reported_incident")
                )

                if att.finalized_at is not None:
                    status = att.close_reason or "submitted"
                    if status == "expired":
                        expired += 1
                    else:
                        submitted += 1
                else:
                    in_progress += 1
                    latest_kind = att_events[-1].kind if att_events else "started"
                    status = "reconnected" if latest_kind == "reconnected" else "working"

                roster.append(
                    RosterProgressRow(
                        candidate_id=cid,
                        display_name=display_name,
                        email=email,
                        enrollment_active=cid in active_set,
                        attempt_id=att.id,
                        status=status,
                        answered_count=answered,
                        total_items=total_items,
                        started_at=att.started_at,
                        deadline_at=att.deadline_at,
                        finalized_at=att.finalized_at,
                        close_reason=att.close_reason,
                        last_saved_at=last_saved,
                        incident_count=incident_count,
                    )
                )

            attempt_owner = {a.id: a.candidate_id for a in attempts}
            incident_views = tuple(
                IncidentEventView(
                    id=ev.id,
                    attempt_id=ev.attempt_id,
                    candidate_id=attempt_owner.get(ev.attempt_id, exam.owner_id),
                    candidate_name=(
                        accounts[attempt_owner[ev.attempt_id]].display_name
                        if attempt_owner.get(ev.attempt_id) in accounts
                        else str(attempt_owner.get(ev.attempt_id, ""))
                    ),
                    kind=ev.kind,
                    recorded_at=ev.recorded_at,
                    note=ev.note,
                )
                for ev in sorted(events, key=lambda e: e.recorded_at, reverse=True)
            )

            ann_views = tuple(
                AnnouncementView(
                    id=ann.id,
                    exam_id=ann.exam_id,
                    author_id=ann.author_id,
                    author_name=accounts[ann.author_id].display_name
                    if ann.author_id in accounts
                    else "Examiner",
                    posted_at=ann.posted_at,
                    message=ann.message,
                )
                for ann in sorted(announcements, key=lambda a: a.posted_at, reverse=True)
            )

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
                counts=MonitorCounts(
                    enrolled=len(active_set),
                    not_started=not_started,
                    in_progress=in_progress,
                    submitted=submitted,
                    expired=expired,
                    finalized=submitted + expired,
                ),
                roster=tuple(roster),
                incidents=incident_views,
                announcements=ann_views,
            )

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
            author_name = accounts[actor.id].display_name if actor.id in accounts else "Examiner"
            return AnnouncementView(
                id=record.id,
                exam_id=record.exam_id,
                author_id=record.author_id,
                author_name=author_name,
                posted_at=record.posted_at,
                message=record.message,
            )

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
            return [
                AnnouncementView(
                    id=ann.id,
                    exam_id=ann.exam_id,
                    author_id=ann.author_id,
                    author_name=accounts[ann.author_id].display_name
                    if ann.author_id in accounts
                    else "Examiner",
                    posted_at=ann.posted_at,
                    message=ann.message,
                )
                for ann in sorted(announcements, key=lambda a: a.posted_at, reverse=True)
            ]
