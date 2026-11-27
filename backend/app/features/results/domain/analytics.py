"""Question-level analytics and class summary computations (FR12, SR05, AT08)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from typing import Iterable
from uuid import UUID

from .grading import compute_attempt_total
from .values import (
    AccountSummary,
    AttemptItemRecord,
    AttemptRecord,
    CENT,
    EnrollmentRecord,
    ExamItemSpec,
    ZERO,
)


@dataclass(frozen=True)
class IncorrectSelectionStat:
    option_no: int
    label: str
    count: int
    exposure_count: int


@dataclass(frozen=True)
class QuestionAnalytics:
    slot: int
    question_id: UUID
    version_id: UUID
    version_no: int
    topic: str
    difficulty: str
    kind: str
    prompt: str
    max_marks: Decimal
    exposure_count: int
    skipped_count: int
    skip_rate: Decimal | None
    skip_rate_display: str
    graded_exposure_count: int
    observed_facility: Decimal | None
    facility_display: str
    common_incorrect_selections: tuple[IncorrectSelectionStat, ...]


@dataclass(frozen=True)
class ClassSummary:
    enrolled_count: int
    finalized_count: int
    in_progress_count: int
    no_show_count: int
    graded_attempt_count: int
    pending_grading_count: int
    mean_score: Decimal | None
    median_score: Decimal | None
    min_score: Decimal | None
    max_score: Decimal | None


def is_item_blank(item: AttemptItemRecord, kind: str) -> bool:
    """Return True when the candidate submitted no response for this item."""
    if kind == "written":
        return not item.written_answer.strip()
    return not any(opt.selected for opt in item.options)


def compute_question_analytics(
    paper_items: Iterable[ExamItemSpec],
    finalized_attempts: Iterable[AttemptRecord],
    items_by_attempt: dict[UUID, list[AttemptItemRecord]],
) -> list[QuestionAnalytics]:
    """Compute per-version analytics solely from real finalized attempts (SR05)."""
    finalized_ids = [a.id for a in finalized_attempts if a.finalized_at is not None]
    exposures_by_slot: dict[int, list[AttemptItemRecord]] = {}
    for attempt_id in finalized_ids:
        for item in items_by_attempt.get(attempt_id, ()):
            exposures_by_slot.setdefault(item.slot, []).append(item)

    results: list[QuestionAnalytics] = []
    for spec in sorted(paper_items, key=lambda s: s.slot):
        exposures = [
            it for it in exposures_by_slot.get(spec.slot, ()) if it.version_id == spec.version_id
        ]
        exposure_count = len(exposures)
        skipped_count = sum(1 for it in exposures if is_item_blank(it, spec.kind))

        if exposure_count > 0:
            skip_rate = (Decimal(skipped_count) / Decimal(exposure_count)).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
            skip_rate_display = f"{skipped_count}/{exposure_count}"
        else:
            skip_rate = None
            skip_rate_display = "No data"

        graded = [it for it in exposures if it.awarded_marks is not None]
        graded_count = len(graded)
        if graded_count > 0:
            avg_fraction = sum(
                (it.awarded_marks / spec.max_marks for it in graded if it.awarded_marks is not None),
                Decimal("0"),
            ) / Decimal(graded_count)
            observed_facility = avg_fraction.quantize(CENT, rounding=ROUND_HALF_UP)
            facility_display = f"{observed_facility:.2f}"
        else:
            observed_facility = None
            facility_display = "No data"

        incorrect_stats: tuple[IncorrectSelectionStat, ...] = ()
        if spec.kind in ("single", "multiple") and exposure_count > 0:
            wrong_options = {opt.option_no: opt.label for opt in spec.options if not opt.is_correct}
            counts: dict[int, int] = {}
            for it in exposures:
                for opt in it.options:
                    if opt.selected and opt.option_no in wrong_options:
                        counts[opt.option_no] = counts.get(opt.option_no, 0) + 1
            incorrect_stats = tuple(
                IncorrectSelectionStat(
                    option_no=opt_no,
                    label=wrong_options[opt_no],
                    count=count,
                    exposure_count=exposure_count,
                )
                for opt_no, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
            )

        results.append(
            QuestionAnalytics(
                slot=spec.slot,
                question_id=spec.question_id,
                version_id=spec.version_id,
                version_no=spec.version_no,
                topic=spec.topic,
                difficulty=spec.difficulty,
                kind=spec.kind,
                prompt=spec.prompt,
                max_marks=spec.max_marks,
                exposure_count=exposure_count,
                skipped_count=skipped_count,
                skip_rate=skip_rate,
                skip_rate_display=skip_rate_display,
                graded_exposure_count=graded_count,
                observed_facility=observed_facility,
                facility_display=facility_display,
                common_incorrect_selections=incorrect_stats,
            )
        )
    return results


def compute_class_summary(
    enrollments: Iterable[EnrollmentRecord],
    attempts: Iterable[AttemptRecord],
    items_by_attempt: dict[UUID, list[AttemptItemRecord]],
) -> ClassSummary:
    """Summarize class performance across real finalized and graded attempts."""
    active_candidates = {e.candidate_id for e in enrollments if e.active}
    attempt_list = list(attempts)
    started_candidates = {a.candidate_id for a in attempt_list}
    no_show_count = len(active_candidates - started_candidates)

    finalized = [a for a in attempt_list if a.finalized_at is not None]
    in_progress_count = len(attempt_list) - len(finalized)

    totals: list[Decimal] = []
    for a in finalized:
        items = items_by_attempt.get(a.id, ())
        total = compute_attempt_total(it.awarded_marks for it in items)
        if total is not None:
            totals.append(total)

    graded_count = len(totals)
    pending_count = len(finalized) - graded_count

    if graded_count > 0:
        mean_val = (sum(totals, ZERO) / Decimal(graded_count)).quantize(CENT, rounding=ROUND_HALF_UP)
        median_raw = median(totals)
        median_val = Decimal(str(median_raw)).quantize(CENT, rounding=ROUND_HALF_UP)
        min_val = min(totals).quantize(CENT, rounding=ROUND_HALF_UP)
        max_val = max(totals).quantize(CENT, rounding=ROUND_HALF_UP)
    else:
        mean_val = median_val = min_val = max_val = None

    return ClassSummary(
        enrolled_count=len(active_candidates),
        finalized_count=len(finalized),
        in_progress_count=in_progress_count,
        no_show_count=no_show_count,
        graded_attempt_count=graded_count,
        pending_grading_count=pending_count,
        mean_score=mean_val,
        median_score=median_val,
        min_score=min_val,
        max_score=max_val,
    )


@dataclass(frozen=True)
class ScoreLine:
    """One finalized attempt's standing: who, how much is graded, and the total."""

    attempt: AttemptRecord
    display_name: str
    email: str
    graded_count: int
    item_count: int
    total_score: Decimal | None

    @property
    def fully_graded(self) -> bool:
        return self.total_score is not None


class ScoreRegister:
    """Finalized attempts with totals, alphabetical by candidate.

    Built once and used by both the results view and the class summary PDF,
    so the score on screen and the score in the export cannot disagree (SR02).
    """

    def __init__(self, lines: Iterable[ScoreLine]) -> None:
        self.lines = tuple(lines)

    @classmethod
    def build(cls, attempts: Iterable[AttemptRecord],
              items_by_attempt: dict[UUID, list[AttemptItemRecord]],
              accounts: dict[UUID, "AccountSummary"]) -> "ScoreRegister":
        lines = []
        for attempt in attempts:
            if attempt.finalized_at is None:
                continue
            items = items_by_attempt.get(attempt.id, ())
            account = accounts.get(attempt.candidate_id)
            lines.append(ScoreLine(
                attempt=attempt,
                display_name=account.display_name if account else str(attempt.candidate_id),
                email=account.email if account else "",
                graded_count=sum(1 for it in items if it.awarded_marks is not None),
                item_count=len(items),
                total_score=compute_attempt_total(it.awarded_marks for it in items),
            ))
        return cls(sorted(lines, key=lambda line: line.display_name.lower()))

    def __iter__(self):
        return iter(self.lines)

    def __len__(self) -> int:
        return len(self.lines)
