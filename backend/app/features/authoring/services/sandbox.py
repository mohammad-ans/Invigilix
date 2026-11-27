"""Examiner sandbox (SR03): render the paper as a candidate would, with no writes.

The unit of work is opened read-only and never committed, so attempt counts,
grades, incidents, reports and analytics are identical before and after a
preview. Simulated answers and the simulated submission live in the browser's
transient preview adapter, never on the server.
"""
from __future__ import annotations

from uuid import UUID

from ..domain import FrozenPaper
from ..ports import EXAMINER, Actor
from .base import AuthoringService
from .views import SandboxPaper


class SandboxService(AuthoringService):
    def open(self, actor: Actor, exam_id: UUID) -> SandboxPaper:
        self._require(actor, EXAMINER)
        with self._uow() as uow:
            exam = self._owned_exam(uow, actor, exam_id)
            bank = uow.questions.versions(i.version_id for i in exam.items)
            paper = FrozenPaper.of(exam, {k: v.version for k, v in bank.items()})
            now = uow.now()
            return SandboxPaper(exam, paper.candidate_items(), now,
                                now + exam.details.schedule.duration)
