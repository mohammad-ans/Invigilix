"""End-to-end acceptance tests (AT06, AT07, AT08, AT09) on memory and SQL backends."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

from pypdf import PdfReader
import pytest

from backend.app.features.results import ADMIN, Actor, CANDIDATE, EXAMINER
from backend.app.features.results.domain import (
    Conflict,
    Forbidden,
    NotFound,
    ValidationFailed,
)


def _seed_at07_paper(harness, owner_id):
    opens = datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc)
    closes = datetime(2026, 11, 27, 11, 0, tzinfo=timezone.utc)
    return harness.create_exam(
        owner_id=owner_id,
        title="Field ecology",
        opens_at=opens,
        closes_at=closes,
        duration_seconds=1800,
        total_marks="10.00",
        published_at=opens - timedelta(hours=1),
        items=[
            {
                "topic": "Ecology",
                "difficulty": "easy",
                "prompt": "Which factor is abiotic?",
                "kind": "single",
                "marking_rule": "exact",
                "max_marks": "2.00",
                "options": [(1, "Light intensity", True), (2, "Population count", False)],
            },
            {
                "topic": "Diversity",
                "difficulty": "medium",
                "prompt": "Which measurements describe species diversity?",
                "kind": "multiple",
                "marking_rule": "partial_no_wrong",
                "max_marks": "4.00",
                "options": [
                    (1, "Species richness", True),
                    (2, "Air temperature", False),
                    (3, "Relative abundance", True),
                ],
            },
            {
                "topic": "Sampling",
                "difficulty": "hard",
                "prompt": "Why repeat the survey on a second transect?",
                "kind": "written",
                "marking_rule": "manual",
                "max_marks": "4.00",
                "rubric": "Mention replication and habitat representativeness.",
            },
        ],
    )


def test_at06_monitor_neutral_incidents_and_announcements(harness):
    owner = harness.add_account(email="remy@example.test", display_name="Remy Chen", roles={EXAMINER})
    other_examiner = harness.add_account(email="ola@example.test", display_name="Ola", roles={EXAMINER})
    admin = harness.add_account(email="admin@example.test", display_name="Admin", roles={ADMIN})
    c1 = harness.add_account(email="eli@example.test", display_name="Eli Brooks", roles={CANDIDATE})
    c2 = harness.add_account(email="nora@example.test", display_name="Nora Khan", roles={CANDIDATE})
    outsider = harness.add_account(email="out@example.test", display_name="Outsider", roles={CANDIDATE})

    exam = _seed_at07_paper(harness, owner.id)
    harness.enroll(exam_id=exam.id, candidate_id=c1.id, enrolled_by=owner.id, active=True)
    harness.enroll(exam_id=exam.id, candidate_id=c2.id, enrolled_by=owner.id, active=True)

    t0 = exam.opens_at + timedelta(minutes=2)
    att1 = harness.create_attempt(
        exam=exam,
        candidate_id=c1.id,
        started_at=t0,
        responses={1: {"selected": [1], "saved_at": t0 + timedelta(minutes=1)}},
        events=[
            ("started", t0, None),
            ("reconnected", t0 + timedelta(minutes=5), "Connection restored after brief drop"),
        ],
    )

    # Monitor shows real active attempt, answered count, and neutral reconnect observation
    snap = harness.module.monitor.get_monitor(owner, exam.id)
    assert snap.status == "ongoing"
    assert snap.counts.enrolled == 2
    assert snap.counts.in_progress == 1
    assert snap.counts.not_started == 1
    assert snap.counts.finalized == 0

    eli_row = next(r for r in snap.roster if r.candidate_id == c1.id)
    assert eli_row.attempt_id == att1.id
    assert eli_row.status == "reconnected"
    assert eli_row.answered_count == 1
    assert eli_row.total_items == 3
    assert eli_row.incident_count == 1
    assert len(snap.incidents) == 2

    # Post announcement and verify candidate receives it
    ann = harness.module.monitor.post_announcement(owner, exam.id, "Check units on Question 3.")
    assert ann.message == "Check units on Question 3."
    cand_feed = harness.module.monitor.list_announcements(c1, exam.id)
    assert len(cand_feed) == 1
    assert cand_feed[0].message == "Check units on Question 3."

    # Authorization boundaries
    with pytest.raises(NotFound):
        harness.module.monitor.get_monitor(other_examiner, exam.id)
    with pytest.raises(Forbidden):
        harness.module.monitor.get_monitor(c1, exam.id)
    with pytest.raises(Forbidden):
        harness.module.monitor.get_monitor(admin, exam.id)
    with pytest.raises(NotFound):
        harness.module.monitor.list_announcements(outsider, exam.id)

    # Blank announcement rejected
    with pytest.raises(ValidationFailed):
        harness.module.monitor.post_announcement(owner, exam.id, "   ")


def test_at07_and_at09_grade_release_pdf_and_verify(harness):
    owner = harness.add_account(email="remy@example.test", display_name="Remy Chen", roles={EXAMINER})
    c1 = harness.add_account(email="sana@example.test", display_name="Sana Ali", roles={CANDIDATE})
    c2 = harness.add_account(email="nora@example.test", display_name="Nora Khan", roles={CANDIDATE})
    exam = _seed_at07_paper(harness, owner.id)
    harness.enroll(exam_id=exam.id, candidate_id=c1.id, enrolled_by=owner.id)
    harness.enroll(exam_id=exam.id, candidate_id=c2.id, enrolled_by=owner.id)

    t_fin = exam.closes_at - timedelta(minutes=4)
    att = harness.create_attempt(
        exam=exam,
        candidate_id=c1.id,
        started_at=exam.opens_at + timedelta(minutes=1),
        finalized_at=t_fin,
        close_reason="submitted",
        responses={
            1: {"selected": [1], "saved_at": t_fin - timedelta(minutes=5)},
            2: {"selected": [1], "saved_at": t_fin - timedelta(minutes=3)},  # {A} of {A,C} -> 2.00
            3: {"written": "Replication improves spatial coverage.", "saved_at": t_fin - timedelta(minutes=1)},
        },
        events=[
            ("started", exam.opens_at + timedelta(minutes=1), None),
            ("reconnected", exam.opens_at + timedelta(minutes=8), "Brief network drop"),
            ("submitted", t_fin, None),
        ],
    )

    # Marking queue shows pending written item with rubric for owner
    queue = harness.module.grading.get_marking_queue(owner, exam.id)
    assert queue.pending_written_count == 1
    assert len(queue.items) == 1
    assert queue.items[0].rubric == "Mention replication and habitat representativeness."

    # Early release before close & before grading fails (FR12)
    with pytest.raises(Conflict) as early_err:
        harness.module.results.publish_results(owner, exam.id)
    assert early_err.value.code == "exam_not_closed"

    # Candidate cannot read unreleased result (returns 404)
    with pytest.raises(NotFound):
        harness.module.results.get_candidate_result(c1, att.id)

    # Out-of-bounds manual grade 5/4 fails
    with pytest.raises(ValidationFailed):
        harness.module.grading.grade_written_item(owner, att.id, 3, "5.00")

    # Cannot manually override objective item
    with pytest.raises(Conflict) as obj_err:
        harness.module.grading.grade_written_item(owner, att.id, 1, "1.00")
    assert obj_err.value.code == "item_not_written"

    # Award 3/4 -> total 7.00 / 10.00 (reconnect incident had zero penalty)
    graded = harness.module.grading.grade_written_item(owner, att.id, 3, "3.00")
    assert graded.awarded_marks == Decimal("3.00")
    assert graded.attempt_total_score == Decimal("7.00")

    # Still before scheduled close -> early release still fails
    with pytest.raises(Conflict) as early_err2:
        harness.module.results.publish_results(owner, exam.id)
    assert early_err2.value.code == "exam_not_closed"

    # Advance past closes_at and publish results
    harness.clock.set(exam.closes_at + timedelta(minutes=5))
    published = harness.module.results.publish_results(owner, exam.id)
    assert published.results_published_at is not None
    assert published.summary.mean_score == Decimal("7.00")
    assert published.attempts[0].total_score == Decimal("7.00")

    # Grades are frozen once released
    with pytest.raises(Conflict) as frozen_err:
        harness.module.grading.grade_written_item(owner, att.id, 3, "4.00")
    assert frozen_err.value.code == "results_already_released"

    # Candidate reads own released result (7/10); other candidate gets 404
    cand_res = harness.module.results.get_candidate_result(c1, att.id)
    assert cand_res.total_score == Decimal("7.00")
    assert cand_res.max_marks == Decimal("10.00")
    assert len(cand_res.verification_code) >= 22  # >= 128 bits entropy
    assert len(cand_res.sha256_hex) == 64
    with pytest.raises(NotFound):
        harness.module.results.get_candidate_result(c2, att.id)

    # AT09: PDF downloads, byte-for-byte repeatability, content check, and public verifier
    dl1 = harness.module.reports.download_candidate_report(c1, att.id)
    dl2 = harness.module.reports.download_candidate_report(c1, att.id)
    assert dl1.pdf_bytes == dl2.pdf_bytes
    assert dl1.pdf_bytes.startswith(b"%PDF-")

    reader = PdfReader(BytesIO(dl1.pdf_bytes))
    pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "7.00 / 10.00" in pdf_text
    assert "Field ecology" in pdf_text
    assert cand_res.verification_code in pdf_text
    # Rubrics must NEVER leak into candidate PDF
    assert "habitat representativeness" not in pdf_text

    # Original digest verifies; altered PDF digest fails; wrong code fails
    assert harness.module.reports.verify_report(cand_res.verification_code, cand_res.sha256_hex) is True
    tampered_bytes = dl1.pdf_bytes + b"\n%tampered"
    import hashlib
    tampered_hex = hashlib.sha256(tampered_bytes).hexdigest()
    assert harness.module.reports.verify_report(cand_res.verification_code, tampered_hex) is False
    assert harness.module.reports.verify_report("wrong-code", cand_res.sha256_hex) is False

    # Owner class summary PDF matches scores and omits candidate-specific secrets safely
    class_dl = harness.module.reports.download_class_report(owner, exam.id)
    assert class_dl.pdf_bytes.startswith(b"%PDF-")
    class_text = "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(class_dl.pdf_bytes)).pages)
    assert "7.00 / 10.00" in class_text
    assert "Sana Ali" in class_text

    with pytest.raises(Forbidden):
        harness.module.reports.download_class_report(c1, exam.id)


def test_at08_end_to_end_analytics_with_blank_and_full_credit(harness):
    owner = harness.add_account(email="remy@example.test", display_name="Remy", roles={EXAMINER})
    c1 = harness.add_account(email="c1@example.test", display_name="Cand One", roles={CANDIDATE})
    c2 = harness.add_account(email="c2@example.test", display_name="Cand Two", roles={CANDIDATE})
    c3 = harness.add_account(email="c3@example.test", display_name="No Show", roles={CANDIDATE})

    opens = datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc)
    closes = datetime(2026, 11, 27, 11, 0, tzinfo=timezone.utc)
    exam = harness.create_exam(
        owner_id=owner.id,
        title="Sampling check",
        opens_at=opens,
        closes_at=closes,
        total_marks="4.00",
        published_at=opens - timedelta(hours=1),
        items=[
            {
                "topic": "Sampling",
                "difficulty": "medium",
                "prompt": "Pick quadrat rule.",
                "kind": "single",
                "marking_rule": "exact",
                "max_marks": "4.00",
                "options": [(1, "Regular intervals", True), (2, "Random guess", False)],
            }
        ],
    )
    for c in (c1, c2, c3):
        harness.enroll(exam_id=exam.id, candidate_id=c.id, enrolled_by=owner.id)

    # c1: blank finalized; c2: full credit finalized; c3: no-show
    harness.create_attempt(
        exam=exam,
        candidate_id=c1.id,
        finalized_at=closes,
        close_reason="expired",
        responses={1: {"selected": []}},
    )
    harness.create_attempt(
        exam=exam,
        candidate_id=c2.id,
        finalized_at=closes - timedelta(minutes=2),
        close_reason="submitted",
        responses={1: {"selected": [1]}},
    )

    res = harness.module.results.get_exam_results(owner, exam.id)
    assert res.summary.enrolled_count == 3
    assert res.summary.finalized_count == 2
    assert res.summary.no_show_count == 1
    assert res.summary.mean_score == Decimal("2.00")

    q = res.question_analytics[0]
    assert q.exposure_count == 2
    assert q.skipped_count == 1
    assert q.skip_rate_display == "1/2"
    assert q.observed_facility == Decimal("0.50")
    assert q.facility_display == "0.50"
