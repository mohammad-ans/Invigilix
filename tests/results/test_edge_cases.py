"""Edge-case, security, multi-role, and rollback atomicity tests for results."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from backend.app.features.results import CANDIDATE, EXAMINER, PdfRenderer, ResultsModule
from backend.app.features.results.domain import Conflict, Forbidden, NotFound


def test_disabled_actor_and_multirole_isolation(harness):
    owner = harness.add_account(email="owner@example.test", display_name="Owner", roles={EXAMINER})
    dual = harness.add_account(
        email="dual@example.test",
        display_name="Dual Role",
        roles={EXAMINER, CANDIDATE},
    )
    disabled = harness.add_account(
        email="off@example.test",
        display_name="Disabled",
        roles={EXAMINER, CANDIDATE},
        enabled=False,
    )

    opens = datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc)
    closes = datetime(2026, 11, 27, 11, 0, tzinfo=timezone.utc)
    exam = harness.create_exam(
        owner_id=owner.id,
        title="Dual isolation",
        opens_at=opens,
        closes_at=closes,
        total_marks="4.00",
        published_at=opens - timedelta(hours=1),
        items=[
            {
                "topic": "Ecology",
                "difficulty": "easy",
                "prompt": "Q1",
                "kind": "single",
                "marking_rule": "exact",
                "max_marks": "4.00",
                "options": [(1, "A", True), (2, "B", False)],
            }
        ],
    )
    harness.enroll(exam_id=exam.id, candidate_id=dual.id, enrolled_by=owner.id, active=True)
    att = harness.create_attempt(
        exam=exam,
        candidate_id=dual.id,
        finalized_at=closes - timedelta(minutes=1),
        close_reason="submitted",
        responses={1: {"selected": [1]}},
    )
    harness.module.monitor.post_announcement(owner, exam.id, "Reminder: check units.")

    # Dual-role user is enrolled candidate on owner's exam -> can read announcements, cannot monitor/grade
    assert len(harness.module.monitor.list_announcements(dual, exam.id)) == 1
    with pytest.raises(NotFound):
        harness.module.monitor.get_monitor(dual, exam.id)
    with pytest.raises(NotFound):
        harness.module.grading.get_marking_queue(dual, exam.id)

    # Disabled account blocked even with roles
    with pytest.raises(Forbidden):
        harness.module.monitor.get_monitor(disabled, exam.id)
    with pytest.raises(Forbidden):
        harness.module.results.get_candidate_result(disabled, att.id)


def test_announcement_lifecycle_and_inactive_enrollment(harness):
    owner = harness.add_account(email="owner@example.test", display_name="Owner", roles={EXAMINER})
    inactive_cand = harness.add_account(email="in@example.test", display_name="Inactive", roles={CANDIDATE})
    opens = datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc)
    closes = datetime(2026, 11, 27, 11, 0, tzinfo=timezone.utc)

    draft_exam = harness.create_exam(
        owner_id=owner.id,
        title="Draft",
        opens_at=opens,
        closes_at=closes,
        total_marks="2.00",
        published_at=None,
        items=[
            {
                "topic": "T",
                "difficulty": "easy",
                "prompt": "P",
                "kind": "single",
                "marking_rule": "exact",
                "max_marks": "2.00",
                "options": [(1, "A", True), (2, "B", False)],
            }
        ],
    )
    with pytest.raises(Conflict) as e1:
        harness.module.monitor.post_announcement(owner, draft_exam.id, "Too early")
    assert e1.value.code == "exam_not_published"

    live_exam = harness.create_exam(
        owner_id=owner.id,
        title="Live",
        opens_at=opens,
        closes_at=closes,
        total_marks="2.00",
        published_at=opens - timedelta(hours=1),
        items=[
            {
                "topic": "T",
                "difficulty": "easy",
                "prompt": "P",
                "kind": "single",
                "marking_rule": "exact",
                "max_marks": "2.00",
                "options": [(1, "A", True), (2, "B", False)],
            }
        ],
    )
    harness.enroll(exam_id=live_exam.id, candidate_id=inactive_cand.id, enrolled_by=owner.id, active=False)
    with pytest.raises(NotFound):
        harness.module.monitor.list_announcements(inactive_cand, live_exam.id)

    harness.clock.set(closes)
    with pytest.raises(Conflict) as e2:
        harness.module.monitor.post_announcement(owner, live_exam.id, "After close")
    assert e2.value.code == "exam_closed"


def test_common_incorrect_selections_regrade_and_zero_exposure_state(harness):
    owner = harness.add_account(email="owner@example.test", display_name="Owner", roles={EXAMINER})
    c1 = harness.add_account(email="c1@example.test", display_name="C1", roles={CANDIDATE})
    c2 = harness.add_account(email="c2@example.test", display_name="C2", roles={CANDIDATE})
    c3 = harness.add_account(email="c3@example.test", display_name="C3", roles={CANDIDATE})
    opens = datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc)
    closes = datetime(2026, 11, 27, 11, 0, tzinfo=timezone.utc)

    exam = harness.create_exam(
        owner_id=owner.id,
        title="Distractor analysis",
        opens_at=opens,
        closes_at=closes,
        total_marks="6.00",
        published_at=opens - timedelta(hours=1),
        items=[
            {
                "topic": "Ecology",
                "difficulty": "medium",
                "prompt": "Select correct choice.",
                "kind": "single",
                "marking_rule": "exact",
                "max_marks": "2.00",
                "options": [(1, "Correct", True), (2, "Distractor X", False), (3, "Distractor Y", False)],
            },
            {
                "topic": "Writing",
                "difficulty": "hard",
                "prompt": "Short note.",
                "kind": "written",
                "marking_rule": "manual",
                "max_marks": "4.00",
            },
        ],
    )
    for c in (c1, c2, c3):
        harness.enroll(exam_id=exam.id, candidate_id=c.id, enrolled_by=owner.id)

    # Zero finalized exposures initially -> No data
    empty_res = harness.module.results.get_exam_results(owner, exam.id)
    assert empty_res.summary.no_show_count == 3
    assert empty_res.summary.mean_score is None
    assert empty_res.question_analytics[0].skip_rate_display == "No data"
    assert empty_res.question_analytics[0].facility_display == "No data"

    # c1 picks Distractor X, c2 picks Distractor X, c3 picks Distractor Y; c1 writes text, c2 blank, c3 open
    a1 = harness.create_attempt(
        exam=exam,
        candidate_id=c1.id,
        finalized_at=closes - timedelta(minutes=2),
        close_reason="submitted",
        responses={1: {"selected": [2]}, 2: {"written": "Draft response"}},
    )
    harness.create_attempt(
        exam=exam,
        candidate_id=c2.id,
        finalized_at=closes - timedelta(minutes=1),
        close_reason="submitted",
        responses={1: {"selected": [2]}, 2: {"written": ""}},
    )
    a3_open = harness.create_attempt(
        exam=exam,
        candidate_id=c3.id,
        finalized_at=None,
        close_reason=None,
        responses={1: {"selected": [3]}},
    )

    # Cannot grade unfinalized attempt
    with pytest.raises(Conflict) as e_unfin:
        harness.module.grading.grade_written_item(owner, a3_open.id, 2, "2.00")
    assert e_unfin.value.code == "attempt_not_finalized"

    # Re-grading before release updates score cleanly
    g1 = harness.module.grading.grade_written_item(owner, a1.id, 2, "2.00")
    assert g1.attempt_total_score == Decimal("2.00")
    g2 = harness.module.grading.grade_written_item(owner, a1.id, 2, "3.50")
    assert g2.attempt_total_score == Decimal("3.50")

    res = harness.module.results.get_exam_results(owner, exam.id)
    q1 = res.question_analytics[0]
    assert q1.exposure_count == 2  # a3_open excluded
    assert len(q1.common_incorrect_selections) == 1
    assert q1.common_incorrect_selections[0].label == "Distractor X"
    assert q1.common_incorrect_selections[0].count == 2
    assert q1.common_incorrect_selections[0].exposure_count == 2

    # Cannot release while a3_open is unfinalized
    harness.clock.set(closes + timedelta(minutes=2))
    with pytest.raises(Conflict) as e_rel:
        harness.module.results.publish_results(owner, exam.id)
    assert e_rel.value.code == "attempts_not_finalized"


def test_publish_rolls_back_completely_on_pdf_failure(harness):
    owner = harness.add_account(email="owner@example.test", display_name="Owner", roles={EXAMINER})
    cand = harness.add_account(email="cand@example.test", display_name="Cand", roles={CANDIDATE})
    opens = datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc)
    closes = datetime(2026, 11, 27, 11, 0, tzinfo=timezone.utc)
    exam = harness.create_exam(
        owner_id=owner.id,
        title="Atomic release",
        opens_at=opens,
        closes_at=closes,
        total_marks="2.00",
        published_at=opens - timedelta(hours=1),
        items=[
            {
                "topic": "Ecology",
                "difficulty": "easy",
                "prompt": "Q1",
                "kind": "single",
                "marking_rule": "exact",
                "max_marks": "2.00",
                "options": [(1, "A", True), (2, "B", False)],
            }
        ],
    )
    harness.enroll(exam_id=exam.id, candidate_id=cand.id, enrolled_by=owner.id)
    att = harness.create_attempt(
        exam=exam,
        candidate_id=cand.id,
        finalized_at=closes,
        close_reason="expired",
        responses={1: {"selected": [1]}},
    )
    harness.clock.set(closes + timedelta(minutes=1))

    class FailingPdf(PdfRenderer):
        def render_candidate_report(self, **kwargs) -> bytes:
            raise RuntimeError("Simulated renderer crash")

        def render_class_summary(self, **kwargs) -> bytes:
            raise RuntimeError("Simulated renderer crash")

    broken_module = ResultsModule(harness.uow_factory, FailingPdf())
    with pytest.raises(RuntimeError):
        broken_module.results.publish_results(owner, exam.id)

    # Transaction rolled back: exam remains unreleased and no report persisted
    after = harness.module.results.get_exam_results(owner, exam.id)
    assert after.results_published_at is None
    with pytest.raises(NotFound):
        harness.module.results.get_candidate_result(cand, att.id)
