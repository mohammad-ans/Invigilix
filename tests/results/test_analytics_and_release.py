"""Analytics (SR05 / AT08) and release gating (FR12) domain tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from backend.app.features.results.domain import (
    AttemptItemRecord,
    AttemptOptionRecord,
    AttemptRecord,
    EnrollmentRecord,
    ExamItemSpec,
    ExamRecord,
    OptionSpec,
    compute_class_summary,
    compute_question_analytics,
    release_blockers,
)


def _exam(opens: datetime, closes: datetime, published: datetime | None = None, released: datetime | None = None) -> ExamRecord:
    return ExamRecord(
        id=uuid4(),
        owner_id=uuid4(),
        title="Biology",
        instructions="Read carefully.",
        opens_at=opens,
        closes_at=closes,
        duration_seconds=1800,
        total_marks=Decimal("8.00"),
        shuffle_objective=False,
        shuffle_choices=False,
        published_at=published or (opens - timedelta(hours=1)),
        results_published_at=released,
    )


def test_at08_analytics_denominators_skip_rate_facility_and_empty_exposures():
    opens = datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc)
    closes = datetime(2026, 11, 27, 11, 0, tzinfo=timezone.utc)
    exam = _exam(opens, closes)

    q1_ver = uuid4()
    q2_ver = uuid4()
    spec1 = ExamItemSpec(
        exam_id=exam.id,
        slot=1,
        version_id=q1_ver,
        question_id=uuid4(),
        version_no=1,
        topic="Ecology",
        difficulty="medium",
        prompt="Identify the abiotic factor.",
        kind="single",
        marking_rule="exact",
        rubric=None,
        max_marks=Decimal("4.00"),
        options=(
            OptionSpec(1, "Light intensity", True),
            OptionSpec(2, "Oak population", False),
            OptionSpec(3, "Herbivory", False),
        ),
    )
    spec2 = ExamItemSpec(
        exam_id=exam.id,
        slot=2,
        version_id=q2_ver,
        question_id=uuid4(),
        version_no=1,
        topic="Sampling",
        difficulty="hard",
        prompt="Unused item in another subset",
        kind="written",
        marking_rule="manual",
        rubric="Explain replication",
        max_marks=Decimal("4.00"),
        options=(),
    )

    c1, c2, c3, c4 = uuid4(), uuid4(), uuid4(), uuid4()
    enrollments = [
        EnrollmentRecord(exam.id, cid, exam.owner_id, True) for cid in (c1, c2, c3, c4)
    ]

    # c1: finalized, blank on slot 1 (0/4) and blank written on slot 2 (0/4)
    a1 = AttemptRecord(uuid4(), exam.id, c1, opens, closes, closes - timedelta(minutes=5), "submitted")
    # c2: finalized, full credit on slot 1 (4/4), blank on slot 2 -> wait: to test zero exposures on spec2, omit spec2 or test a separate version!
    a2 = AttemptRecord(uuid4(), exam.id, c2, opens, closes, closes - timedelta(minutes=3), "submitted")
    # c3: no-show (enrolled, no attempt)
    # c4: still in progress (unfinalized, must NOT count toward finalized exposures)
    a4 = AttemptRecord(uuid4(), exam.id, c4, opens, closes, None, None)

    items_by_attempt = {
        a1.id: [
            AttemptItemRecord(
                a1.id, exam.id, 1, q1_ver, 1, "", False, 0, None, Decimal("0.00"), None,
                options=(
                    AttemptOptionRecord(a1.id, 1, q1_ver, 1, 1, False),
                    AttemptOptionRecord(a1.id, 1, q1_ver, 2, 2, False),
                    AttemptOptionRecord(a1.id, 1, q1_ver, 3, 3, False),
                ),
            )
        ],
        a2.id: [
            AttemptItemRecord(
                a2.id, exam.id, 1, q1_ver, 1, "", False, 1, opens + timedelta(minutes=2), Decimal("4.00"), None,
                options=(
                    AttemptOptionRecord(a2.id, 1, q1_ver, 1, 1, True),
                    AttemptOptionRecord(a2.id, 1, q1_ver, 2, 2, False),
                    AttemptOptionRecord(a2.id, 1, q1_ver, 3, 3, False),
                ),
            )
        ],
        a4.id: [
            AttemptItemRecord(
                a4.id, exam.id, 1, q1_ver, 1, "", False, 1, opens + timedelta(minutes=1), None, None,
                options=(
                    AttemptOptionRecord(a4.id, 1, q1_ver, 1, 1, False),
                    AttemptOptionRecord(a4.id, 1, q1_ver, 2, 2, True),
                    AttemptOptionRecord(a4.id, 1, q1_ver, 3, 3, False),
                ),
            )
        ],
    }

    analytics = compute_question_analytics([spec1, spec2], [a1, a2, a4], items_by_attempt)
    q1_stat, q2_stat = analytics

    # Slot 1: 2 finalized exposures (1 blank = 0/4, 1 full credit = 4/4)
    assert q1_stat.exposure_count == 2
    assert q1_stat.skipped_count == 1
    assert q1_stat.skip_rate_display == "1/2"
    assert q1_stat.skip_rate == Decimal("0.5000")
    assert q1_stat.graded_exposure_count == 2
    assert q1_stat.observed_facility == Decimal("0.50")
    assert q1_stat.facility_display == "0.50"
    # Unfinalized a4 chose option 2, must NOT leak into incorrect selections
    assert q1_stat.common_incorrect_selections == ()

    # Slot 2: zero finalized exposures -> "No data"
    assert q2_stat.exposure_count == 0
    assert q2_stat.skip_rate is None
    assert q2_stat.skip_rate_display == "No data"
    assert q2_stat.observed_facility is None
    assert q2_stat.facility_display == "No data"

    summary = compute_class_summary(enrollments, [a1, a2, a4], items_by_attempt)
    assert summary.enrolled_count == 4
    assert summary.finalized_count == 2
    assert summary.in_progress_count == 1
    assert summary.no_show_count == 1
    assert summary.graded_attempt_count == 2
    assert summary.mean_score == Decimal("2.00")


def test_release_blockers_cover_close_finalization_and_pending_grades():
    opens = datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc)
    closes = datetime(2026, 11, 27, 11, 0, tzinfo=timezone.utc)
    exam = _exam(opens, closes)
    att = AttemptRecord(uuid4(), exam.id, uuid4(), opens, closes, None, None)
    items = {
        att.id: [AttemptItemRecord(att.id, exam.id, 1, uuid4(), 1, "answer", False, 1, None, None, None)]
    }

    # Before close + unfinalized
    blockers = release_blockers(exam, [att], items, closes - timedelta(minutes=1))
    codes = {b.code for b in blockers}
    assert "exam_not_closed" in codes
    assert "attempts_not_finalized" in codes

    # Finalized but ungraded after close
    att_done = AttemptRecord(att.id, exam.id, att.candidate_id, opens, closes, closes, "expired")
    blockers2 = release_blockers(exam, [att_done], items, closes + timedelta(minutes=1))
    assert [b.code for b in blockers2] == ["grading_incomplete"]

    # Graded and after close -> ready
    items_graded = {
        att.id: [AttemptItemRecord(att.id, exam.id, 1, uuid4(), 1, "answer", False, 1, None, Decimal("3.00"), exam.owner_id)]
    }
    assert release_blockers(exam, [att_done], items_graded, closes) == []
