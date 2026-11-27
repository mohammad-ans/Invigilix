"""Shared plumbing for authoring use cases: transactions, roles and record scope."""
from __future__ import annotations

from typing import Callable
from uuid import UUID, uuid4

from ..domain import Exam, Forbidden, NotFound, Question
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
    def _owned_question(uow: UnitOfWork, actor: Actor, question_id: UUID, *,
                        lock: bool = False) -> Question:
        question = uow.questions.get(question_id, lock=lock)
        if question is None or not question.owned_by(actor.id):
            raise NotFound("Question")
        return question
