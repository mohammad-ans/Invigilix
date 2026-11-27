"""Exam configuration and publication use cases (FR03, FR05)."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ..domain import (
    Exam, ExamDetails, FrozenPaper, Issue, NotFound, PaperItem, PublicationPolicy,
    ValidationFailed, parse_marks,
)
from ..ports import EXAMINER, Actor, UnitOfWork
from .base import AuthoringService, IdFactory, UnitOfWorkFactory
from .views import ExamOverview, ExamSummary, SlotView


@dataclass(frozen=True)
class SlotRequest:
    """The examiner's intent for one slot. ``version_id`` pins a specific revision;
    otherwise an existing assignment keeps its version and a new one takes the latest."""

    question_id: UUID
    max_marks: object
    version_id: UUID | None = None


class ExamService(AuthoringService):
    def __init__(self, unit_of_work: UnitOfWorkFactory, ids: IdFactory | None = None,
                 policy: PublicationPolicy | None = None) -> None:
        super().__init__(unit_of_work, ids)
        self._policy = policy or PublicationPolicy()

    # -- queries ---------------------------------------------------------------
    def list_owned(self, actor: Actor) -> list[ExamSummary]:
        self._require(actor, EXAMINER)
        with self._uow() as uow:
            now = uow.now()
            exams = sorted(uow.exams.owned_by(actor.id),
                           key=lambda e: e.details.schedule.opens_at, reverse=True)
            return [ExamSummary(e, e.state_at(now),
                                sum(1 for x in uow.enrollments.for_exam(e.id) if x.active))
                    for e in exams]

    def overview(self, actor: Actor, exam_id: UUID) -> ExamOverview:
        self._require(actor, EXAMINER)
        with self._uow() as uow:
            return self._overview(uow, self._owned_exam(uow, actor, exam_id))

    # -- commands --------------------------------------------------------------
    def create_draft(self, actor: Actor, details: ExamDetails) -> ExamOverview:
        self._require(actor, EXAMINER)
        with self._uow() as uow:
            exam = Exam(self._ids(), actor.id, details)
            uow.exams.add(exam)
            view = self._overview(uow, exam)
            uow.commit()
            return view

    def update_draft(self, actor: Actor, exam_id: UUID, details: ExamDetails) -> ExamOverview:
        self._require(actor, EXAMINER)
        with self._uow() as uow:
            exam = self._owned_exam(uow, actor, exam_id, lock=True)
            exam.revise(details)
            uow.exams.save(exam)
            view = self._overview(uow, exam)
            uow.commit()
            return view

    def assign(self, actor: Actor, exam_id: UUID, requests: list[SlotRequest]) -> ExamOverview:
        """Replace the draft paper. Each slot pins an owned question version (FR04)."""
        self._require(actor, EXAMINER)
        with self._uow() as uow:
            exam = self._owned_exam(uow, actor, exam_id, lock=True)
            pinned = {i.question_id: i.version_id for i in exam.items}
            items, issues = [], []
            for slot, request in enumerate(requests, start=1):
                item, slot_issues = self._resolve_slot(uow, actor, slot, request, pinned)
                issues.extend(slot_issues)
                if item is not None:
                    items.append(item)
            if issues:
                raise ValidationFailed(issues)
            exam.assign(items)
            uow.exams.save(exam)
            view = self._overview(uow, exam)
            uow.commit()
            return view

    def duplicate(self, actor: Actor, exam_id: UUID) -> ExamOverview:
        """Start a new draft from an owned exam in any state. No roster is copied."""
        self._require(actor, EXAMINER)
        with self._uow() as uow:
            source = self._owned_exam(uow, actor, exam_id)
            copy = source.duplicate(self._ids(), actor.id)
            uow.exams.add(copy)
            view = self._overview(uow, copy)
            uow.commit()
            return view

    def publish(self, actor: Actor, exam_id: UUID) -> ExamOverview:
        """Validate under the exam lock, then freeze the paper (FR05)."""
        self._require(actor, EXAMINER)
        with self._uow() as uow:
            exam = self._owned_exam(uow, actor, exam_id, lock=True)
            bank = uow.questions.versions(i.version_id for i in exam.items)
            exam.publish(uow.now(), bank, self._policy)
            uow.exams.save(exam)
            view = self._overview(uow, exam)
            uow.commit()
            return view

    @staticmethod
    def _resolve_slot(uow: UnitOfWork, actor: Actor, slot: int, request: SlotRequest,
                      pinned: dict[UUID, UUID]) -> tuple[PaperItem | None, list[Issue]]:
        """Turn one slot request into a pinned item, or the reasons it cannot be one.

        Version choice: an explicit ``version_id`` wins; otherwise an existing
        assignment keeps its pin (FR04); otherwise the bank's latest version.
        """
        issues: list[Issue] = []
        marks, marks_issue = parse_marks(request.max_marks, "max_marks")
        if marks_issue:
            issues.append(marks_issue.located(item=slot))
        question = uow.questions.get(request.question_id)
        if question is None or not question.owned_by(actor.id):
            issues.append(Issue("question_unavailable", "This question is not in your bank.",
                                field="question_id", item=slot))
            return None, issues
        version_id = request.version_id or pinned.get(question.id) or question.latest.id
        if question.version(version_id) is None:
            issues.append(Issue("unknown_version", "That version does not belong to this question.",
                                field="version_id", item=slot))
            return None, issues
        if marks is None:
            return None, issues
        return PaperItem(slot, question.id, version_id, marks), issues

    # -- handoff to delivery ---------------------------------------------------
    def frozen_paper(self, exam_id: UUID) -> FrozenPaper:
        """Server-side boundary for delivery. Includes keys; never return it to a client."""
        with self._uow() as uow:
            exam = uow.exams.get(exam_id)
            if exam is None or not exam.is_published:
                raise NotFound("Exam")
            bank = uow.questions.versions(i.version_id for i in exam.items)
            return FrozenPaper.of(exam, {k: v.version for k, v in bank.items()})

    # -- helpers ---------------------------------------------------------------
    def _overview(self, uow: UnitOfWork, exam: Exam) -> ExamOverview:
        now = uow.now()
        bank = uow.questions.versions(i.version_id for i in exam.items)
        slots = []
        for item in exam.items:
            entry = bank.get(item.version_id)
            if entry is None:
                continue
            question = uow.questions.get(item.question_id)
            latest = question.latest.number if question else entry.version.number
            slots.append(SlotView(item, entry.version, latest))
        return ExamOverview(exam, exam.state_at(now), tuple(slots),
                            self._policy.review(exam, bank, now), now)
