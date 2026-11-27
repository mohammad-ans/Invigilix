"""Enrollment and the entry policy that decides who may start an exam (FR06)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from .exam import Exam, ExamState
from .values import Change

CANDIDATE_ROLE = "candidate"


@dataclass(frozen=True)
class AccountRecord:
    """The identity facts authoring needs. Owned by the foundation identity service."""

    id: UUID
    email: str
    display_name: str
    enabled: bool
    roles: frozenset[str]

    @property
    def is_candidate(self) -> bool:
        return CANDIDATE_ROLE in self.roles


@dataclass
class Enrollment:
    """A candidate's place on one exam's roster. Withdrawn, never deleted."""

    exam_id: UUID
    candidate_id: UUID
    enrolled_by: UUID
    active: bool = True

    @staticmethod
    def admission(existing: "Enrollment | None") -> Change:
        """What admitting this candidate would change. Planning and execution share it."""
        if existing is None:
            return Change.CREATED
        return Change.UNCHANGED if existing.active else Change.UPDATED

    def set_active(self, active: bool) -> Change:
        if self.active == active:
            return Change.UNCHANGED
        self.active = active
        return Change.UPDATED


class Access(StrEnum):
    """Why a candidate can or cannot enter, phrased for the roster and dashboard."""

    AVAILABLE = "available"
    UPCOMING = "upcoming"
    COMPLETED = "completed"
    AWAITING_PUBLICATION = "awaiting_publication"
    ENROLLMENT_INACTIVE = "enrollment_inactive"
    ACCOUNT_DISABLED = "account_disabled"
    NOT_CANDIDATE = "not_candidate"
    NOT_ENROLLED = "not_enrolled"


@dataclass(frozen=True)
class EntryDecision:
    access: Access

    @property
    def can_start(self) -> bool:
        return self.access is Access.AVAILABLE

    @property
    def visible_to_candidate(self) -> bool:
        """Published metadata and instructions are visible once the entry is valid."""
        return self.access in (Access.AVAILABLE, Access.UPCOMING, Access.COMPLETED)


class EntryPolicy:
    """Entry needs an active account, the candidate role, an active enrollment and
    an open window evaluated against server time. A client clock never counts."""

    def decide(self, exam: Exam, account: AccountRecord | None,
               enrollment: Enrollment | None, now: datetime) -> EntryDecision:
        if account is None or enrollment is None:
            return EntryDecision(Access.NOT_ENROLLED)
        if not account.enabled:
            return EntryDecision(Access.ACCOUNT_DISABLED)
        if not account.is_candidate:
            return EntryDecision(Access.NOT_CANDIDATE)
        if not enrollment.active:
            return EntryDecision(Access.ENROLLMENT_INACTIVE)
        state = exam.state_at(now)
        return EntryDecision({
            ExamState.DRAFT: Access.AWAITING_PUBLICATION,
            ExamState.SCHEDULED: Access.UPCOMING,
            ExamState.ONGOING: Access.AVAILABLE,
            ExamState.COMPLETED: Access.COMPLETED,
        }[state])
