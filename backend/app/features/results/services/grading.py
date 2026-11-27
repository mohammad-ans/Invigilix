"""Examiner manual grading workflow for finalized written items (FR11, AT07)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from ..domain import (
    Conflict,
    ExamStatus,
    NotFound,
    compute_attempt_total,
    derive_exam_status,
    validate_manual_award,
)
from ..ports import Actor
from .base import UowFactory, load_owned_exam, require_examiner


@dataclass(frozen=True)
class MarkingItemView:
    attempt_id: UUID
    candidate_id: UUID
    candidate_name: str
    candidate_email: str
    slot: int
    display_no: int
    topic: str
    difficulty: str
    prompt: str
    rubric: str | None
    written_answer: str
    max_marks: Decimal
    awarded_marks: Decimal | None
    graded_by: UUID | None
    graded_by_name: str | None
    finalized_at: datetime
    close_reason: str


@dataclass(frozen=True)
class MarkingQueueView:
    exam_id: UUID
    exam_title: str
    status: ExamStatus
    results_published_at: datetime | None
    unfinalized_attempts: int
    pending_written_count: int
    graded_written_count: int
    items: tuple[MarkingItemView, ...]


@dataclass(frozen=True)
class GradeUpdateResult:
    attempt_id: UUID
    exam_id: UUID
    slot: int
    awarded_marks: Decimal
    max_marks: Decimal
    graded_by: UUID
    graded_count: int
    item_count: int
    attempt_total_score: Decimal | None


class GradingService:
    """Owner-only review and scoring of finalized written responses."""

    def __init__(self, uow_factory: UowFactory) -> None:
        self._uow = uow_factory

    def get_marking_queue(self, actor: Actor, exam_id: UUID) -> MarkingQueueView:
        with self._uow() as uow:
            exam = load_owned_exam(uow, actor, exam_id)
            now = uow.now()
            paper = {spec.slot: spec for spec in uow.exams.paper_items(exam.id)}
            attempts = uow.attempts.for_exam(exam.id)
            items_by_attempt = uow.attempts.items_for_exam(exam.id)

            finalized = [a for a in attempts if a.finalized_at is not None]
            unfinalized_count = len(attempts) - len(finalized)

            grader_ids = {
                it.graded_by
                for att in finalized
                for it in items_by_attempt.get(att.id, ())
                if it.graded_by is not None
            }
            accounts = uow.accounts.by_ids({a.candidate_id for a in finalized} | grader_ids)

            marking_items: list[MarkingItemView] = []
            pending = 0
            graded = 0
            for att in sorted(finalized, key=lambda a: (a.finalized_at or now, str(a.id))):
                cand = accounts.get(att.candidate_id)
                cand_name = cand.display_name if cand else str(att.candidate_id)
                cand_email = cand.email if cand else ""
                for it in sorted(items_by_attempt.get(att.id, ()), key=lambda x: x.slot):
                    spec = paper.get(it.slot)
                    if spec is None or spec.kind != "written":
                        continue
                    if it.awarded_marks is None:
                        pending += 1
                    else:
                        graded += 1
                    grader = accounts.get(it.graded_by) if it.graded_by else None
                    marking_items.append(
                        MarkingItemView(
                            attempt_id=att.id,
                            candidate_id=att.candidate_id,
                            candidate_name=cand_name,
                            candidate_email=cand_email,
                            slot=it.slot,
                            display_no=it.display_no,
                            topic=spec.topic,
                            difficulty=spec.difficulty,
                            prompt=spec.prompt,
                            rubric=spec.rubric,
                            written_answer=it.written_answer,
                            max_marks=spec.max_marks,
                            awarded_marks=it.awarded_marks,
                            graded_by=it.graded_by,
                            graded_by_name=grader.display_name if grader else None,
                            finalized_at=att.finalized_at,
                            close_reason=att.close_reason or "submitted",
                        )
                    )

            return MarkingQueueView(
                exam_id=exam.id,
                exam_title=exam.title,
                status=derive_exam_status(exam, now),
                results_published_at=exam.results_published_at,
                unfinalized_attempts=unfinalized_count,
                pending_written_count=pending,
                graded_written_count=graded,
                items=tuple(marking_items),
            )

    def grade_written_item(
        self,
        actor: Actor,
        attempt_id: UUID,
        slot: int,
        awarded_marks: Decimal | int | float | str,
    ) -> GradeUpdateResult:
        require_examiner(actor)
        with self._uow() as uow:
            attempt_probe = uow.attempts.get(attempt_id)
            if attempt_probe is None:
                raise NotFound("Attempt")

            # Lock exam before attempt to respect the schema's deadlock-free order.
            exam = uow.exams.get(attempt_probe.exam_id, lock=True)
            if exam is None or exam.owner_id != actor.id:
                raise NotFound("Attempt")

            attempt = uow.attempts.get(attempt_id, lock=True)
            if attempt is None:
                raise NotFound("Attempt")

            if exam.results_published_at is not None:
                raise Conflict(
                    "results_already_released",
                    "Results have been released and awards are now frozen.",
                )

            if attempt.finalized_at is None:
                raise Conflict(
                    "attempt_not_finalized",
                    "Only finalized attempts can be graded.",
                )

            paper = {spec.slot: spec for spec in uow.exams.paper_items(exam.id)}
            spec = paper.get(slot)
            att_items = uow.attempts.items_for_attempt(attempt.id)
            target = next((it for it in att_items if it.slot == slot), None)
            if spec is None or target is None:
                raise NotFound("Attempt item")

            if spec.kind != "written":
                raise Conflict(
                    "item_not_written",
                    "Objective items are auto-scored and cannot be manually graded.",
                )

            award = validate_manual_award(awarded_marks, spec.max_marks)
            uow.attempts.set_item_award(attempt.id, slot, award, actor.id)

            updated_awards = [
                award if it.slot == slot else it.awarded_marks for it in att_items
            ]
            graded_count = sum(1 for a in updated_awards if a is not None)
            total_score = compute_attempt_total(updated_awards)

            uow.commit()
            return GradeUpdateResult(
                attempt_id=attempt.id,
                exam_id=exam.id,
                slot=slot,
                awarded_marks=award,
                max_marks=spec.max_marks,
                graded_by=actor.id,
                graded_count=graded_count,
                item_count=len(att_items),
                attempt_total_score=total_score,
            )
