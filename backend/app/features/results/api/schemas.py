"""Pydantic request and response schemas for the results FastAPI router.

Marks and normalized decimal rates serialize as fixed-point strings ("7.00", "0.50")
to preserve exact NUMERIC(8,2) values across JSON boundaries.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints

from ..domain import ExamStatus, QuestionAnalytics
from ..services import (
    AnnouncementView,
    CandidateAttemptScoreView,
    CandidateResultItemView,
    CandidateResultView,
    ExamResultsView,
    GradeUpdateResult,
    IncidentEventView,
    MarkingItemView,
    MarkingQueueView,
    MonitorCounts,
    MonitorSnapshot,
    ReleaseBlockerView,
    RosterProgressRow,
)

FixedDecimal = Annotated[
    Decimal,
    PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json"),
]
ShortText = Annotated[str, StringConstraints(max_length=256)]


class InModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# -- Requests -----------------------------------------------------------------


class AnnouncementIn(InModel):
    message: str = Field(max_length=4000)


class GradeIn(InModel):
    awarded_marks: Decimal | int | float | str


class VerifyReportIn(InModel):
    verification_code: ShortText
    sha256_hex: ShortText


# -- Monitor & Announcements (FR10) -------------------------------------------


class MonitorCountsOut(BaseModel):
    enrolled: int
    not_started: int
    in_progress: int
    submitted: int
    expired: int
    finalized: int

    @classmethod
    def of(cls, c: MonitorCounts) -> "MonitorCountsOut":
        return cls(**c.__dict__)


class RosterProgressOut(BaseModel):
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

    @classmethod
    def of(cls, r: RosterProgressRow) -> "RosterProgressOut":
        return cls(**r.__dict__)


class IncidentEventOut(BaseModel):
    id: UUID
    attempt_id: UUID
    candidate_id: UUID
    candidate_name: str
    kind: str
    recorded_at: datetime
    note: str | None

    @classmethod
    def of(cls, ev: IncidentEventView) -> "IncidentEventOut":
        return cls(**ev.__dict__)


class AnnouncementOut(BaseModel):
    id: UUID
    exam_id: UUID
    author_id: UUID
    author_name: str
    posted_at: datetime
    message: str

    @classmethod
    def of(cls, ann: AnnouncementView) -> "AnnouncementOut":
        return cls(**ann.__dict__)


class MonitorOut(BaseModel):
    exam_id: UUID
    exam_title: str
    status: ExamStatus
    opens_at: datetime
    closes_at: datetime
    published_at: datetime | None
    results_published_at: datetime | None
    server_time: datetime
    total_items: int
    counts: MonitorCountsOut
    roster: list[RosterProgressOut]
    incidents: list[IncidentEventOut]
    announcements: list[AnnouncementOut]

    @classmethod
    def of(cls, snap: MonitorSnapshot) -> "MonitorOut":
        return cls(
            exam_id=snap.exam_id,
            exam_title=snap.exam_title,
            status=snap.status,
            opens_at=snap.opens_at,
            closes_at=snap.closes_at,
            published_at=snap.published_at,
            results_published_at=snap.results_published_at,
            server_time=snap.server_time,
            total_items=snap.total_items,
            counts=MonitorCountsOut.of(snap.counts),
            roster=[RosterProgressOut.of(r) for r in snap.roster],
            incidents=[IncidentEventOut.of(ev) for ev in snap.incidents],
            announcements=[AnnouncementOut.of(a) for a in snap.announcements],
        )


# -- Grading & Marking (FR11) -------------------------------------------------


class MarkingItemOut(BaseModel):
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
    max_marks: FixedDecimal
    awarded_marks: FixedDecimal | None
    graded_by: UUID | None
    graded_by_name: str | None
    finalized_at: datetime
    close_reason: str

    @classmethod
    def of(cls, item: MarkingItemView) -> "MarkingItemOut":
        return cls(**item.__dict__)


class MarkingQueueOut(BaseModel):
    exam_id: UUID
    exam_title: str
    status: ExamStatus
    results_published_at: datetime | None
    unfinalized_attempts: int
    pending_written_count: int
    graded_written_count: int
    items: list[MarkingItemOut]

    @classmethod
    def of(cls, q: MarkingQueueView) -> "MarkingQueueOut":
        return cls(
            exam_id=q.exam_id,
            exam_title=q.exam_title,
            status=q.status,
            results_published_at=q.results_published_at,
            unfinalized_attempts=q.unfinalized_attempts,
            pending_written_count=q.pending_written_count,
            graded_written_count=q.graded_written_count,
            items=[MarkingItemOut.of(it) for it in q.items],
        )


class GradeUpdateOut(BaseModel):
    attempt_id: UUID
    exam_id: UUID
    slot: int
    awarded_marks: FixedDecimal
    max_marks: FixedDecimal
    graded_by: UUID
    graded_count: int
    item_count: int
    attempt_total_score: FixedDecimal | None

    @classmethod
    def of(cls, g: GradeUpdateResult) -> "GradeUpdateOut":
        return cls(**g.__dict__)


# -- Examiner Results & Analytics (FR12, SR05) --------------------------------


class ReleaseBlockerOut(BaseModel):
    code: str
    message: str
    field: str | None = None
    item: int | None = None

    @classmethod
    def of(cls, b: ReleaseBlockerView) -> "ReleaseBlockerOut":
        return cls(**b.__dict__)


class ClassSummaryOut(BaseModel):
    enrolled_count: int
    finalized_count: int
    in_progress_count: int
    no_show_count: int
    graded_attempt_count: int
    pending_grading_count: int
    mean_score: FixedDecimal | None
    median_score: FixedDecimal | None
    min_score: FixedDecimal | None
    max_score: FixedDecimal | None


class CandidateAttemptScoreOut(BaseModel):
    attempt_id: UUID
    candidate_id: UUID
    display_name: str
    email: str
    close_reason: str
    finalized_at: datetime
    graded_count: int
    item_count: int
    total_score: FixedDecimal | None
    max_marks: FixedDecimal
    status: str
    verification_code: str | None

    @classmethod
    def of(cls, row: CandidateAttemptScoreView) -> "CandidateAttemptScoreOut":
        return cls(**row.__dict__)


class IncorrectSelectionOut(BaseModel):
    option_no: int
    label: str
    count: int
    exposure_count: int


class QuestionAnalyticsOut(BaseModel):
    slot: int
    question_id: UUID
    version_id: UUID
    version_no: int
    topic: str
    difficulty: str
    kind: str
    prompt: str
    max_marks: FixedDecimal
    exposure_count: int
    skipped_count: int
    skip_rate: float | None
    skip_rate_display: str
    graded_exposure_count: int
    observed_facility: FixedDecimal | None
    facility_display: str
    common_incorrect_selections: list[IncorrectSelectionOut]

    @classmethod
    def of(cls, q: QuestionAnalytics) -> "QuestionAnalyticsOut":
        return cls(
            slot=q.slot,
            question_id=q.question_id,
            version_id=q.version_id,
            version_no=q.version_no,
            topic=q.topic,
            difficulty=q.difficulty,
            kind=q.kind,
            prompt=q.prompt,
            max_marks=q.max_marks,
            exposure_count=q.exposure_count,
            skipped_count=q.skipped_count,
            skip_rate=float(q.skip_rate) if q.skip_rate is not None else None,
            skip_rate_display=q.skip_rate_display,
            graded_exposure_count=q.graded_exposure_count,
            observed_facility=q.observed_facility,
            facility_display=q.facility_display,
            common_incorrect_selections=[
                IncorrectSelectionOut(
                    option_no=s.option_no,
                    label=s.label,
                    count=s.count,
                    exposure_count=s.exposure_count,
                )
                for s in q.common_incorrect_selections
            ],
        )


class ExamResultsOut(BaseModel):
    exam_id: UUID
    exam_title: str
    status: ExamStatus
    opens_at: datetime
    closes_at: datetime
    total_marks: FixedDecimal
    published_at: datetime | None
    results_published_at: datetime | None
    server_time: datetime
    can_release: bool
    release_blockers: list[ReleaseBlockerOut]
    summary: ClassSummaryOut
    attempts: list[CandidateAttemptScoreOut]
    question_analytics: list[QuestionAnalyticsOut]

    @classmethod
    def of(cls, view: ExamResultsView) -> "ExamResultsOut":
        return cls(
            exam_id=view.exam_id,
            exam_title=view.exam_title,
            status=view.status,
            opens_at=view.opens_at,
            closes_at=view.closes_at,
            total_marks=view.total_marks,
            published_at=view.published_at,
            results_published_at=view.results_published_at,
            server_time=view.server_time,
            can_release=view.can_release,
            release_blockers=[ReleaseBlockerOut.of(b) for b in view.release_blockers],
            summary=ClassSummaryOut(**view.summary.__dict__),
            attempts=[CandidateAttemptScoreOut.of(a) for a in view.attempts],
            question_analytics=[QuestionAnalyticsOut.of(q) for q in view.question_analytics],
        )


# -- Candidate Result & Public Verifier (FR12, SR02, SR06) --------------------


class CandidateSelectedOptionOut(BaseModel):
    option_no: int
    label: str


class CandidateResultItemOut(BaseModel):
    """Candidate-safe item summary: strictly excludes keys and rubrics."""

    slot: int
    display_no: int
    kind: Literal["single", "multiple", "written"]
    prompt: str
    max_marks: FixedDecimal
    awarded_marks: FixedDecimal
    flagged: bool
    written_answer: str | None
    selected_options: list[CandidateSelectedOptionOut]

    @classmethod
    def of(cls, item: CandidateResultItemView) -> "CandidateResultItemOut":
        return cls(
            slot=item.slot,
            display_no=item.display_no,
            kind=item.kind,
            prompt=item.prompt,
            max_marks=item.max_marks,
            awarded_marks=item.awarded_marks,
            flagged=item.flagged,
            written_answer=item.written_answer,
            selected_options=[
                CandidateSelectedOptionOut(option_no=o.option_no, label=o.label)
                for o in item.selected_options
            ],
        )


class CandidateResultOut(BaseModel):
    attempt_id: UUID
    exam_id: UUID
    exam_title: str
    candidate_id: UUID
    candidate_name: str
    finalized_at: datetime
    close_reason: str
    results_published_at: datetime
    total_score: FixedDecimal
    max_marks: FixedDecimal
    verification_code: str
    sha256_hex: str
    report_download_path: str
    items: list[CandidateResultItemOut]

    @classmethod
    def of(cls, view: CandidateResultView) -> "CandidateResultOut":
        return cls(
            attempt_id=view.attempt_id,
            exam_id=view.exam_id,
            exam_title=view.exam_title,
            candidate_id=view.candidate_id,
            candidate_name=view.candidate_name,
            finalized_at=view.finalized_at,
            close_reason=view.close_reason,
            results_published_at=view.results_published_at,
            total_score=view.total_score,
            max_marks=view.max_marks,
            verification_code=view.verification_code,
            sha256_hex=view.sha256_hex,
            report_download_path=f"/me/attempts/{view.attempt_id}/report",
            items=[CandidateResultItemOut.of(it) for it in view.items],
        )


class VerifyReportOut(BaseModel):
    """Public verification response: returns validity only."""

    valid: bool
