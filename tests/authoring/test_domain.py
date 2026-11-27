"""Domain rules for questions, exams, publication and entry (FR03–FR06)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.features.authoring.domain import (
    Access, AccountRecord, AnswerOption, AssignedVersion, Conflict, Difficulty, EntryPolicy,
    Enrollment, Exam, ExamDetails, ExamState, FrozenPaper, MarkingRule, PaperItem,
    PublicationPolicy, Question, QuestionContent, QuestionKind, ValidationFailed,
)

UTC = timezone.utc
OPENS = datetime(2026, 11, 27, 10, 30, tzinfo=UTC)
CLOSES = datetime(2026, 11, 27, 11, 0, tzinfo=UTC)


def single(prompt="Which factor is abiotic?", keys=(1,)):
    return QuestionContent("Ecology", Difficulty.EASY, QuestionKind.SINGLE, prompt,
                           MarkingRule.EXACT, tuple(AnswerOption(i, label, i in keys)
                                                    for i, label in [(1, "Light"), (2, "Rabbit")]))


def codes(error: ValidationFailed) -> set[str]:
    return {i.code for i in error.issues}


def details(total="10", **overrides):
    values = dict(title="Field ecology", instructions="Answer all.", opens_at=OPENS,
                  closes_at=CLOSES, duration_minutes=30, total_marks=total)
    values.update(overrides)
    return ExamDetails.build(**values)


class TestQuestionContent:
    def test_single_answer_needs_exactly_one_key(self):
        assert {i.code for i in single(keys=(1, 2)).issues()} == {"single_key_count"}
        assert {i.code for i in single(keys=()).issues()} == {"single_key_count"}
        assert single().issues() == []

    def test_objective_needs_two_options(self):
        content = QuestionContent("T", Difficulty.HARD, QuestionKind.MULTIPLE, "Pick",
                                  MarkingRule.PARTIAL_NO_WRONG, (AnswerOption(1, "A", True),))
        assert "too_few_options" in {i.code for i in content.issues()}

    def test_written_takes_no_options_and_manual_rule(self):
        content = QuestionContent("T", Difficulty.MEDIUM, QuestionKind.WRITTEN, "Explain",
                                  MarkingRule.EXACT, (AnswerOption(1, "A"),))
        assert {i.code for i in content.issues()} == {"rule_mismatch", "written_has_options"}

    def test_duplicate_option_ids_and_labels_refused(self):
        content = QuestionContent("T", Difficulty.EASY, QuestionKind.MULTIPLE, "Pick",
                                  MarkingRule.EXACT,
                                  (AnswerOption(1, "Same", True), AnswerOption(1, " same ")))
        found = {i.code for i in content.normalized().issues()}
        assert {"duplicate_option_id", "duplicate_option_label"} <= found


class TestQuestionVersions:
    def test_edit_appends_and_history_is_preserved(self):
        question = Question.create(uuid4(), uuid4(), uuid4(), single())
        first = question.latest
        second, created = question.revise(uuid4(), single("Which factor is non-living?"))
        assert created and second.number == 2
        assert question.version(first.id).content.prompt == "Which factor is abiotic?"

    def test_identical_edit_is_not_a_new_version(self):
        question = Question.create(uuid4(), uuid4(), uuid4(), single())
        version, created = question.revise(uuid4(), single("  Which factor is abiotic?  "))
        assert not created and version.number == 1 and len(question.versions) == 1

    def test_invalid_revision_is_refused(self):
        question = Question.create(uuid4(), uuid4(), uuid4(), single())
        with pytest.raises(ValidationFailed):
            question.revise(uuid4(), single(keys=(1, 2)))
        assert len(question.versions) == 1


class TestExamDetails:
    def test_reports_every_invalid_particular(self):
        with pytest.raises(ValidationFailed) as caught:
            details(total="0", title=" ", duration_minutes=0, closes_at=OPENS)
        assert codes(caught.value) == {"required", "non_positive_marks", "non_positive_duration",
                                       "close_before_open"}

    def test_naive_times_are_refused(self):
        with pytest.raises(ValidationFailed) as caught:
            details(opens_at=OPENS.replace(tzinfo=None))
        assert codes(caught.value) == {"timezone_required"}

    def test_marks_precision(self):
        with pytest.raises(ValidationFailed) as caught:
            details(total="10.005")
        assert codes(caught.value) == {"marks_precision"}


def paper_exam(caps=("2", "4", "4"), total="10"):
    owner = uuid4()
    exam = Exam(uuid4(), owner, details(total))
    bank, items = {}, []
    for slot, cap in enumerate(caps, start=1):
        question = Question.create(uuid4(), owner, uuid4(), single(f"Prompt {slot}"))
        bank[question.latest.id] = AssignedVersion(question.latest, owner)
        items.append(PaperItem(slot, question.id, question.latest.id, Decimal(cap)))
    exam.assign(items)
    return exam, bank


class TestPublication:
    NOW = OPENS - timedelta(hours=1)

    def test_mismatched_total_blocks_publication(self):
        exam, bank = paper_exam(total="12")
        with pytest.raises(ValidationFailed) as caught:
            exam.publish(self.NOW, bank, PublicationPolicy())
        assert caught.value.code == "paper_invalid"
        assert codes(caught.value) == {"total_mismatch"}
        assert not exam.is_published

    def test_invalid_key_is_reported_against_its_slot(self):
        exam, bank = paper_exam()
        bad = exam.items[1]
        version = bank[bad.version_id].version
        broken = QuestionContent(**{**version.content.__dict__,
                                    "options": tuple(AnswerOption(o.id, o.label, True)
                                                     for o in version.content.options)})
        bank[bad.version_id] = AssignedVersion(
            type(version)(version.id, version.question_id, 1, broken), exam.owner_id)
        report = PublicationPolicy().review(exam, bank, self.NOW)
        assert not report.ready
        assert [(i.code, i.item) for i in report.issues] == [("single_key_count", 2)]

    def test_empty_paper_foreign_question_and_closed_window(self):
        exam, bank = paper_exam()
        intruder = next(iter(bank))
        bank[intruder] = AssignedVersion(bank[intruder].version, uuid4())
        report = PublicationPolicy().review(exam, bank, CLOSES)
        failing = {c.name for c in report.checks if not c.passed}
        assert failing == {"ownership", "window"}
        exam.items = ()
        assert "nonempty" in {c.name for c in PublicationPolicy().review(exam, bank, self.NOW)
                              .checks if not c.passed}

    def test_publish_freezes_the_paper(self):
        exam, bank = paper_exam()
        exam.publish(self.NOW, bank, PublicationPolicy())
        assert exam.state_at(self.NOW) is ExamState.SCHEDULED
        assert exam.state_at(OPENS) is ExamState.ONGOING
        assert exam.state_at(CLOSES) is ExamState.COMPLETED
        with pytest.raises(Conflict):
            exam.revise(details())
        with pytest.raises(Conflict):
            exam.assign([])
        with pytest.raises(Conflict):
            exam.publish(self.NOW, bank, PublicationPolicy())

    def test_duplicate_bank_question_refused_on_assignment(self):
        exam, _ = paper_exam()
        first = exam.items[0]
        with pytest.raises(ValidationFailed) as caught:
            exam.assign([first, PaperItem(2, first.question_id, uuid4(), Decimal("1"))])
        assert codes(caught.value) == {"duplicate_question"}

    def test_candidate_view_omits_keys(self):
        exam, bank = paper_exam()
        exam.publish(self.NOW, bank, PublicationPolicy())
        paper = FrozenPaper.of(exam, {k: v.version for k, v in bank.items()})
        item = paper.candidate_items()[0]
        assert not hasattr(item, "correct_option_ids") and not hasattr(item.options[0], "correct")
        assert paper.items[0].correct_option_ids == (1,)


class TestEntryPolicy:
    def setup_method(self):
        self.exam, bank = paper_exam()
        self.exam.publish(OPENS - timedelta(days=1), bank, PublicationPolicy())
        self.account = AccountRecord(uuid4(), "nora@example.test", "Nora Khan", True,
                                     frozenset({"candidate"}))
        self.enrollment = Enrollment(self.exam.id, self.account.id, self.exam.owner_id)

    def decide(self, now, account=None, enrollment="default"):
        enrollment = self.enrollment if enrollment == "default" else enrollment
        return EntryPolicy().decide(self.exam, account or self.account, enrollment, now)

    def test_window_drives_access(self):
        assert self.decide(OPENS - timedelta(minutes=1)).access is Access.UPCOMING
        assert self.decide(OPENS + timedelta(minutes=12)).can_start
        assert self.decide(CLOSES).access is Access.COMPLETED

    def test_unenrolled_disabled_and_inactive_cannot_start(self):
        during = OPENS + timedelta(minutes=12)
        assert self.decide(during, enrollment=None).access is Access.NOT_ENROLLED
        disabled = AccountRecord(**{**self.account.__dict__, "enabled": False})
        assert self.decide(during, account=disabled).access is Access.ACCOUNT_DISABLED
        examiner = AccountRecord(**{**self.account.__dict__, "roles": frozenset({"examiner"})})
        assert self.decide(during, account=examiner).access is Access.NOT_CANDIDATE
        self.enrollment.active = False
        assert self.decide(during).access is Access.ENROLLMENT_INACTIVE


class TestRosterRulesLiveOnTheEntities:
    """Admission and roster-closure are entity behaviour, shared by service and import."""

    def test_admission_predicts_the_change(self):
        from app.features.authoring.domain import Change

        assert Enrollment.admission(None) is Change.CREATED
        withdrawn = Enrollment(uuid4(), uuid4(), uuid4(), active=False)
        assert Enrollment.admission(withdrawn) is Change.UPDATED
        assert withdrawn.set_active(True) is Change.UPDATED and withdrawn.active
        assert Enrollment.admission(withdrawn) is Change.UNCHANGED
        assert withdrawn.set_active(True) is Change.UNCHANGED

    def test_roster_closes_with_the_window(self):
        exam, bank = paper_exam()
        exam.publish(OPENS - timedelta(days=1), bank, PublicationPolicy())
        exam.ensure_roster_open(OPENS + timedelta(minutes=5))
        with pytest.raises(Conflict) as caught:
            exam.ensure_roster_open(CLOSES)
        assert caught.value.code == "exam_closed"


def test_import_report_records_typed_changes():
    from app.features.authoring.domain import Change
    from app.features.authoring.services import ImportReport

    report = ImportReport(rows=4)
    for change in (Change.CREATED, Change.CREATED, Change.UPDATED, Change.UNCHANGED):
        report.record(change)
    assert (report.created, report.updated, report.unchanged) == (2, 1, 1)
