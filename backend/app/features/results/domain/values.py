"""Immutable domain records and validated value helpers for results."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal
from uuid import UUID

QuestionKind = Literal["single", "multiple", "written"]
MarkingRule = Literal["exact", "partial_no_wrong", "manual"]
CloseReason = Literal["submitted", "expired"]
EventKind = Literal["started", "reconnected", "reported_incident", "submitted", "expired"]
ExamStatus = Literal["draft", "scheduled", "ongoing", "closed", "results_released"]

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def quantize_marks(value: Decimal | int | float | str) -> Decimal:
    """Convert numeric mark input into a two-decimal-place Decimal."""
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid marks.")
    try:
        dec = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid mark value: {value!r}") from exc
    if not dec.is_finite():
        raise ValueError(f"Non-finite mark value: {value!r}")
    return dec.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class AccountSummary:
    id: UUID
    email: str
    display_name: str
    roles: frozenset[str]
    enabled: bool = True


@dataclass(frozen=True)
class OptionSpec:
    option_no: int
    label: str
    is_correct: bool


@dataclass(frozen=True)
class ExamItemSpec:
    exam_id: UUID
    slot: int
    version_id: UUID
    question_id: UUID
    version_no: int
    topic: str
    difficulty: str
    prompt: str
    kind: QuestionKind
    marking_rule: MarkingRule
    rubric: str | None
    max_marks: Decimal
    options: tuple[OptionSpec, ...] = ()


@dataclass(frozen=True)
class ExamRecord:
    id: UUID
    owner_id: UUID
    title: str
    instructions: str
    opens_at: datetime
    closes_at: datetime
    duration_seconds: int
    total_marks: Decimal
    shuffle_objective: bool
    shuffle_choices: bool
    published_at: datetime | None
    results_published_at: datetime | None


@dataclass(frozen=True)
class EnrollmentRecord:
    exam_id: UUID
    candidate_id: UUID
    enrolled_by: UUID
    active: bool


@dataclass(frozen=True)
class AttemptRecord:
    id: UUID
    exam_id: UUID
    candidate_id: UUID
    started_at: datetime
    deadline_at: datetime
    finalized_at: datetime | None
    close_reason: CloseReason | None


@dataclass(frozen=True)
class AttemptOptionRecord:
    attempt_id: UUID
    slot: int
    version_id: UUID
    option_no: int
    display_no: int
    selected: bool


@dataclass(frozen=True)
class AttemptItemRecord:
    attempt_id: UUID
    exam_id: UUID
    slot: int
    version_id: UUID
    display_no: int
    written_answer: str
    flagged: bool
    answer_revision: int
    saved_at: datetime | None
    awarded_marks: Decimal | None
    graded_by: UUID | None
    options: tuple[AttemptOptionRecord, ...] = ()


@dataclass(frozen=True)
class AttemptEventRecord:
    id: UUID
    attempt_id: UUID
    kind: EventKind
    recorded_at: datetime
    note: str | None = None


@dataclass(frozen=True)
class AnnouncementRecord:
    id: UUID
    exam_id: UUID
    author_id: UUID
    posted_at: datetime
    message: str


@dataclass(frozen=True)
class ResultReportRecord:
    verification_code: str
    attempt_id: UUID
    issued_at: datetime
    sha256_hex: str
    pdf_bytes: bytes
