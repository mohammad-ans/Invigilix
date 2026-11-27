"""Shared authorization and transaction helpers for results services."""
from __future__ import annotations

from typing import Callable
from uuid import UUID

from ..domain import ExamRecord, Forbidden, NotFound
from ..ports import Actor, CANDIDATE, EXAMINER, ResultsUnitOfWork

UowFactory = Callable[[], ResultsUnitOfWork]


def require_enabled(actor: Actor) -> None:
    if not actor.enabled:
        raise Forbidden("This account is disabled.")


def require_examiner(actor: Actor) -> None:
    require_enabled(actor)
    if not actor.has(EXAMINER):
        raise Forbidden("Examiner role is required for this action.")


def require_candidate(actor: Actor) -> None:
    require_enabled(actor)
    if not actor.has(CANDIDATE):
        raise Forbidden("Candidate role is required for this action.")


def load_owned_exam(
    uow: ResultsUnitOfWork,
    actor: Actor,
    exam_id: UUID,
    *,
    lock: bool = False,
) -> ExamRecord:
    """Verify examiner role and return the exam only if owned by ``actor``."""
    require_examiner(actor)
    exam = uow.exams.get(exam_id, lock=lock)
    if exam is None or exam.owner_id != actor.id:
        raise NotFound("Exam")
    return exam
