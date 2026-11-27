"""Shared plumbing for authoring use cases: transactions, roles and record scope."""
from __future__ import annotations

from typing import Callable
from uuid import UUID, uuid4

from ..domain import (
    AccountRecord, Change, Enrollment, Exam, Forbidden, Issue, NotFound, Question, ValidationFailed,
)
from ..ports import Actor, UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]
IdFactory = Callable[[], UUID]


class AuthoringService:
    """Base class: each public method opens one unit of work and checks access.

    Role failures raise :class:`Forbidden` (403). Records outside the actor's
    scope raise :class:`NotFound` (404) so their existence is never revealed.
    """

    def __init__(self, unit_of_work: UnitOfWorkFactory, ids: IdFactory | None = None) -> None:
        self._uow = unit_of_work
        self._ids = ids or uuid4

    @staticmethod
    def _require(actor: Actor, role: str) -> None:
        if not actor.has(role):
            raise Forbidden()

    @staticmethod
    def _owned_exam(uow: UnitOfWork, actor: Actor, exam_id: UUID, *, lock: bool = False) -> Exam:
        exam = uow.exams.get(exam_id, lock=lock)
        if exam is None or not exam.owned_by(actor.id):
            raise NotFound("Exam")
        return exam

    @staticmethod
    def _enrollable_candidate(uow: UnitOfWork, email: str,
                              field: str = "candidate_email") -> AccountRecord:
        """The enabled candidate account for ``email``, or a located refusal."""
        def refuse(code: str, message: str) -> ValidationFailed:
            return ValidationFailed([Issue(code, message, field=field)])
        if not email.strip():
            raise refuse("required", "Enter the candidate's email.")
        account = uow.accounts.by_email(email)
        if account is None:
            raise refuse("unknown_candidate", "No account uses this email.")
        if not account.is_candidate:
            raise refuse("not_candidate", "This account does not hold the candidate role.")
        if not account.enabled:
            raise refuse("account_disabled", "This account is disabled.")
        return account

    @staticmethod
    def _admit(uow: UnitOfWork, exam: Exam, candidate_id: UUID, by: UUID) -> Change:
        """Enroll or restore a candidate; the entity decides, the repository persists."""
        existing = uow.enrollments.get(exam.id, candidate_id)
        change = Enrollment.admission(existing)
        if change is Change.CREATED:
            uow.enrollments.add(Enrollment(exam.id, candidate_id, by))
        elif change is Change.UPDATED:
            existing.set_active(True)
            uow.enrollments.save(existing)
        return change

    @staticmethod
    def _owned_question(uow: UnitOfWork, actor: Actor, question_id: UUID, *,
                        lock: bool = False) -> Question:
        question = uow.questions.get(question_id, lock=lock)
        if question is None or not question.owned_by(actor.id):
            raise NotFound("Question")
        return question
