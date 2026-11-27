"""Question bank use cases (FR04)."""
from __future__ import annotations

from uuid import UUID

from ..domain import Question, QuestionContent, QuestionVersion
from ..ports import EXAMINER, Actor, BankQuery
from .base import AuthoringService
from .views import QuestionUsage


class QuestionBankService(AuthoringService):
    def search(self, actor: Actor, query: BankQuery) -> list[Question]:
        self._require(actor, EXAMINER)
        with self._uow() as uow:
            found = uow.questions.search(actor.id, query)
            return sorted(found, key=lambda q: (q.latest.content.topic.casefold(),
                                                q.latest.content.prompt.casefold()))

    def get(self, actor: Actor, question_id: UUID) -> tuple[Question, list[QuestionUsage]]:
        """The question with its full history and where each version is pinned."""
        self._require(actor, EXAMINER)
        with self._uow() as uow:
            question = self._owned_question(uow, actor, question_id)
            numbers = {v.id: v.number for v in question.versions}
            usage = [QuestionUsage(e.id, e.details.title, i.slot, numbers[i.version_id],
                                   e.is_published)
                     for e in uow.exams.owned_by(actor.id) for i in e.items
                     if i.question_id == question.id]
            return question, usage

    def create(self, actor: Actor, content: QuestionContent,
               question_id: UUID | None = None) -> Question:
        self._require(actor, EXAMINER)
        with self._uow() as uow:
            question = Question.create(question_id or self._ids(), actor.id, self._ids(), content)
            uow.questions.add(question)
            uow.commit()
            return question

    def revise(self, actor: Actor, question_id: UUID,
               content: QuestionContent) -> tuple[Question, QuestionVersion, bool]:
        """Append a version. Exams that pinned earlier versions keep them."""
        self._require(actor, EXAMINER)
        with self._uow() as uow:
            question = self._owned_question(uow, actor, question_id, lock=True)
            version, created = question.revise(self._ids(), content)
            if created:
                uow.questions.append_version(question, version)
                uow.commit()
            return question, version, created
