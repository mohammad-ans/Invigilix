"""Exam results review, release gate, question analytics, and candidate result view."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from ..domain import (
    ClassSummary,
    Conflict,
    ExamRecord,
    ExamStatus,
    NotFound,
    QuestionAnalytics,
    ResultReportRecord,
    compute_attempt_total,
    compute_class_summary,
    compute_question_analytics,
    compute_sha256_hex,
    derive_exam_status,
    generate_verification_code,
    release_blockers,
    require_release_ready,
)
from ..ports import (
    Actor,
    CandidateReportItemLine,
    PdfRenderer,
    ResultsUnitOfWork,
)
from .base import UowFactory, load_owned_exam, require_candidate


@dataclass(frozen=True)
class ReleaseBlockerView:
    code: str
    message: str
    field: str | None = None
    item: int | None = None


@dataclass(frozen=True)
class CandidateAttemptScoreView:
    attempt_id: UUID
    candidate_id: UUID
    display_name: str
    email: str
    close_reason: str
    finalized_at: datetime
    graded_count: int
    item_count: int
    total_score: Decimal | None
    max_marks: Decimal
    status: str
    verification_code: str | None


@dataclass(frozen=True)
class ExamResultsView:
    exam_id: UUID
    exam_title: str
    status: ExamStatus
    opens_at: datetime
    closes_at: datetime
    total_marks: Decimal
    published_at: datetime | None
    results_published_at: datetime | None
    server_time: datetime
    can_release: bool
    release_blockers: tuple[ReleaseBlockerView, ...]
    summary: ClassSummary
    attempts: tuple[CandidateAttemptScoreView, ...]
    question_analytics: tuple[QuestionAnalytics, ...]


@dataclass(frozen=True)
class CandidateSelectedOptionView:
    option_no: int
    label: str


@dataclass(frozen=True)
class CandidateResultItemView:
    slot: int
    display_no: int
    kind: str
    prompt: str
    max_marks: Decimal
    awarded_marks: Decimal
    flagged: bool
    written_answer: str | None
    selected_options: tuple[CandidateSelectedOptionView, ...]


@dataclass(frozen=True)
class CandidateResultView:
    attempt_id: UUID
    exam_id: UUID
    exam_title: str
    candidate_id: UUID
    candidate_name: str
    finalized_at: datetime
    close_reason: str
    results_published_at: datetime
    total_score: Decimal
    max_marks: Decimal
    verification_code: str
    sha256_hex: str
    items: tuple[CandidateResultItemView, ...]


class ResultsService:
    """Owner review/release and candidate own-result queries (FR12, SR05, AT07, AT08)."""

    def __init__(self, uow_factory: UowFactory, pdf_renderer: PdfRenderer) -> None:
        self._uow = uow_factory
        self._pdf = pdf_renderer

    def _build_exam_results_view(
        self,
        uow: ResultsUnitOfWork,
        exam: ExamRecord,
        now: datetime,
    ) -> ExamResultsView:
        paper = uow.exams.paper_items(exam.id)
        enrollments = uow.enrollments.for_exam(exam.id)
        attempts = uow.attempts.for_exam(exam.id)
        items_by_attempt = uow.attempts.items_for_exam(exam.id)
        reports_by_attempt = uow.reports.for_exam(exam.id)

        finalized = [a for a in attempts if a.finalized_at is not None]
        accounts = uow.accounts.by_ids(a.candidate_id for a in finalized)

        summary = compute_class_summary(enrollments, attempts, items_by_attempt)
        analytics = compute_question_analytics(paper, finalized, items_by_attempt)
        blockers = tuple(
            ReleaseBlockerView(b.code, b.message, b.field, b.item)
            for b in release_blockers(exam, attempts, items_by_attempt, now)
        )

        attempt_rows: list[CandidateAttemptScoreView] = []
        for att in sorted(
            finalized,
            key=lambda a: (
                accounts.get(a.candidate_id).display_name.lower()
                if a.candidate_id in accounts
                else str(a.candidate_id)
            ),
        ):
            items = items_by_attempt.get(att.id, ())
            graded_count = sum(1 for it in items if it.awarded_marks is not None)
            total = compute_attempt_total(it.awarded_marks for it in items)
            acct = accounts.get(att.candidate_id)
            report = reports_by_attempt.get(att.id)
            row_status = (
                "released"
                if exam.results_published_at is not None
                else ("graded" if total is not None else "pending_grade")
            )
            attempt_rows.append(
                CandidateAttemptScoreView(
                    attempt_id=att.id,
                    candidate_id=att.candidate_id,
                    display_name=acct.display_name if acct else str(att.candidate_id),
                    email=acct.email if acct else "",
                    close_reason=att.close_reason or "submitted",
                    finalized_at=att.finalized_at,
                    graded_count=graded_count,
                    item_count=len(items),
                    total_score=total,
                    max_marks=exam.total_marks,
                    status=row_status,
                    verification_code=report.verification_code if report else None,
                )
            )

        return ExamResultsView(
            exam_id=exam.id,
            exam_title=exam.title,
            status=derive_exam_status(exam, now),
            opens_at=exam.opens_at,
            closes_at=exam.closes_at,
            total_marks=exam.total_marks,
            published_at=exam.published_at,
            results_published_at=exam.results_published_at,
            server_time=now,
            can_release=len(blockers) == 0,
            release_blockers=blockers,
            summary=summary,
            attempts=tuple(attempt_rows),
            question_analytics=tuple(analytics),
        )

    def get_exam_results(self, actor: Actor, exam_id: UUID) -> ExamResultsView:
        with self._uow() as uow:
            exam = load_owned_exam(uow, actor, exam_id)
            now = uow.now()
            return self._build_exam_results_view(uow, exam, now)

    def publish_results(self, actor: Actor, exam_id: UUID) -> ExamResultsView:
        with self._uow() as uow:
            exam = load_owned_exam(uow, actor, exam_id, lock=True)
            now = uow.now()
            attempts = uow.attempts.for_exam(exam.id)
            items_by_attempt = uow.attempts.items_for_exam(exam.id)
            require_release_ready(exam, attempts, items_by_attempt, now)

            paper = {spec.slot: spec for spec in uow.exams.paper_items(exam.id)}
            accounts = uow.accounts.by_ids(a.candidate_id for a in attempts)
            published_exam = uow.exams.set_results_published(exam.id, now)

            for att in attempts:
                if att.finalized_at is None:
                    continue
                if uow.reports.get_by_attempt(att.id) is not None:
                    continue
                att_items = sorted(items_by_attempt.get(att.id, ()), key=lambda it: it.display_no)
                total = compute_attempt_total(it.awarded_marks for it in att_items)
                if total is None:
                    raise Conflict(
                        "grading_incomplete",
                        f"Attempt {att.id} is not fully graded.",
                    )

                candidate = accounts[att.candidate_id]
                report_lines = [
                    CandidateReportItemLine(
                        display_no=it.display_no,
                        slot=it.slot,
                        kind=paper[it.slot].kind,
                        prompt=paper[it.slot].prompt,
                        max_marks=paper[it.slot].max_marks,
                        awarded_marks=it.awarded_marks,
                    )
                    for it in att_items
                    if it.slot in paper and it.awarded_marks is not None
                ]

                code = generate_verification_code()
                while uow.reports.get_by_code(code) is not None:
                    code = generate_verification_code()

                pdf_bytes = self._pdf.render_candidate_report(
                    exam=published_exam,
                    attempt=att,
                    candidate=candidate,
                    total_score=total,
                    verification_code=code,
                    issued_at=now,
                    items=report_lines,
                )
                digest = compute_sha256_hex(pdf_bytes)
                uow.reports.add(
                    ResultReportRecord(
                        verification_code=code,
                        attempt_id=att.id,
                        issued_at=now,
                        sha256_hex=digest,
                        pdf_bytes=pdf_bytes,
                    )
                )

            view = self._build_exam_results_view(uow, published_exam, now)
            uow.commit()
            return view

    def get_candidate_result(self, actor: Actor, attempt_id: UUID) -> CandidateResultView:
        require_candidate(actor)
        with self._uow() as uow:
            attempt = uow.attempts.get(attempt_id)
            if attempt is None or attempt.candidate_id != actor.id or attempt.finalized_at is None:
                raise NotFound("Result")

            exam = uow.exams.get(attempt.exam_id)
            if exam is None or exam.results_published_at is None:
                raise NotFound("Result")

            att_items = sorted(uow.attempts.items_for_attempt(attempt.id), key=lambda it: it.display_no)
            total = compute_attempt_total(it.awarded_marks for it in att_items)
            if total is None:
                raise NotFound("Result")

            report = uow.reports.get_by_attempt(attempt.id)
            if report is None:
                raise NotFound("Result")

            paper = {spec.slot: spec for spec in uow.exams.paper_items(exam.id)}
            accounts = uow.accounts.by_ids([actor.id])
            cand_name = accounts[actor.id].display_name if actor.id in accounts else ""

            item_views: list[CandidateResultItemView] = []
            for it in att_items:
                spec = paper.get(it.slot)
                if spec is None or it.awarded_marks is None:
                    continue
                opt_labels = {opt.option_no: opt.label for opt in spec.options}
                selected = tuple(
                    CandidateSelectedOptionView(
                        option_no=opt.option_no,
                        label=opt_labels.get(opt.option_no, f"Option {opt.option_no}"),
                    )
                    for opt in sorted(it.options, key=lambda o: o.display_no)
                    if opt.selected
                )
                item_views.append(
                    CandidateResultItemView(
                        slot=it.slot,
                        display_no=it.display_no,
                        kind=spec.kind,
                        prompt=spec.prompt,
                        max_marks=spec.max_marks,
                        awarded_marks=it.awarded_marks,
                        flagged=it.flagged,
                        written_answer=it.written_answer if spec.kind == "written" else None,
                        selected_options=selected,
                    )
                )

            return CandidateResultView(
                attempt_id=attempt.id,
                exam_id=exam.id,
                exam_title=exam.title,
                candidate_id=actor.id,
                candidate_name=cand_name,
                finalized_at=attempt.finalized_at,
                close_reason=attempt.close_reason or "submitted",
                results_published_at=exam.results_published_at,
                total_score=total,
                max_marks=exam.total_marks,
                verification_code=report.verification_code,
                sha256_hex=report.sha256_hex,
                items=tuple(item_views),
            )
