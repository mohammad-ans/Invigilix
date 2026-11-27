"""Authoring use cases against the acceptance cases AT02, AT03 and AT06."""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from app.features.authoring.domain import (
    Access, Conflict, ExamState, Forbidden, NotFound, QuestionKind, ValidationFailed,
)
from app.features.authoring.ports import BankQuery
from support import CLOSES, OPENS, SlotRequest, content, marks


def issue_codes(error):
    return {(i.code, i.item) for i in error.value.issues}


class TestAT02PublishAndPreserve:
    """AT02 · FR03 · FR04 · FR05"""

    def test_mismatched_total_cannot_publish_then_fixed_total_publishes(self, world):
        exam_id, _ = world.three_item_paper(total="12")
        actor = world.actor("examiner")
        overview = world.module.exams.overview(actor, exam_id)
        assert not overview.report.ready
        assert overview.exam.allocated_marks == marks("10")
        with pytest.raises(ValidationFailed) as caught:
            world.module.exams.publish(actor, exam_id)
        assert issue_codes(caught) == {("total_mismatch", None)}

        world.module.exams.update_draft(actor, exam_id, world.details("10"))
        published = world.module.exams.publish(actor, exam_id)
        assert published.exam.is_published and published.state is ExamState.SCHEDULED

    def test_single_answer_with_two_keys_is_refused(self, world):
        with pytest.raises(ValidationFailed) as caught:
            world.module.bank.create(world.actor("examiner"), content(keys=(1, 2)))
        assert {i.field for i in caught.value.issues} == {"correct_option_ids"}

    def test_published_paper_retains_original_revision_and_key(self, world):
        exam_id, (q1, *_rest) = world.three_item_paper()
        actor = world.actor("examiner")
        world.module.exams.publish(actor, exam_id)
        original = q1.latest

        edited = content("Which factor is non-living?", keys=(3,))
        _, version, created = world.module.bank.revise(actor, q1.id, edited)
        assert created and version.number == 2

        paper = world.module.exams.frozen_paper(exam_id)
        slot1 = paper.items[0]
        assert slot1.version.id == original.id
        assert slot1.version.content.prompt == "Which factor is abiotic?"
        assert slot1.correct_option_ids == (1,)
        assert paper.total_marks == marks("10")
        assert paper.shuffle_questions and paper.shuffle_choices
        overview = world.module.exams.overview(actor, exam_id)
        assert overview.slots[0].outdated

        _, usage = world.module.bank.get(actor, q1.id)
        assert [(u.version_number, u.frozen) for u in usage] == [(1, True)]

    def test_published_exam_is_frozen(self, world):
        exam_id, questions = world.three_item_paper()
        actor = world.actor("examiner")
        world.module.exams.publish(actor, exam_id)
        with pytest.raises(Conflict):
            world.module.exams.update_draft(actor, exam_id, world.details())
        with pytest.raises(Conflict):
            world.module.exams.assign(actor, exam_id, [SlotRequest(questions[0].id, "10")])

    def test_draft_assignment_keeps_pinned_version_until_repinned(self, world):
        exam_id, (q1, q2, q3) = world.three_item_paper()
        actor = world.actor("examiner")
        world.module.bank.revise(actor, q1.id, content("Revised prompt"))
        requests = [SlotRequest(q.id, m) for q, m in ((q1, "2"), (q2, "4"), (q3, "4"))]
        kept = world.module.exams.assign(actor, exam_id, requests)
        assert kept.slots[0].version.number == 1 and kept.slots[0].outdated
        latest = world.module.bank.get(actor, q1.id)[0].latest
        requests[0] = SlotRequest(q1.id, "2", latest.id)
        repinned = world.module.exams.assign(actor, exam_id, requests)
        assert repinned.slots[0].version.number == 2 and not repinned.slots[0].outdated

    def test_publication_after_close_is_refused(self, world):
        exam_id, _ = world.three_item_paper()
        world.clock.current = CLOSES
        with pytest.raises(ValidationFailed) as caught:
            world.module.exams.publish(world.actor("examiner"), exam_id)
        assert ("window_passed", None) in issue_codes(caught)

    def test_empty_paper_cannot_publish(self, world):
        actor = world.actor("examiner")
        exam = world.module.exams.create_draft(actor, world.details()).exam
        with pytest.raises(ValidationFailed) as caught:
            world.module.exams.publish(actor, exam.id)
        assert ("empty_paper", None) in issue_codes(caught)

    def test_slot_errors_identify_item_and_field(self, world):
        actor = world.actor("examiner")
        exam = world.module.exams.create_draft(actor, world.details()).exam
        mine = world.question()
        foreign = world.question("other")
        with pytest.raises(ValidationFailed) as caught:
            world.module.exams.assign(actor, exam.id, [SlotRequest(mine.id, "0"),
                                                       SlotRequest(foreign.id, "2")])
        assert {(i.code, i.item, i.field) for i in caught.value.issues} == {
            ("non_positive_marks", 1, "max_marks"), ("question_unavailable", 2, "question_id")}


class TestBank:
    """FR04: create, find by topic or difficulty, edit, assign."""

    def test_find_by_topic_difficulty_kind_and_text(self, world):
        actor = world.actor("examiner")
        world.module.bank.create(actor, content("Quadrat sizes", topic="Sampling"))
        world.module.bank.create(actor, content("Explain bias", QuestionKind.WRITTEN,
                                                topic="Sampling"))
        world.question("other", "Someone else's")
        search = world.module.bank.search
        assert len(search(actor, BankQuery(topic="sampling"))) == 2
        assert len(search(actor, BankQuery(kind=QuestionKind.WRITTEN))) == 1
        assert [q.latest.content.prompt for q in search(actor, BankQuery(text="quadrat"))] == [
            "Quadrat sizes"]
        assert search(actor, BankQuery(text="someone")) == []

    def test_other_examiners_question_is_not_found(self, world):
        foreign = world.question("other")
        with pytest.raises(NotFound):
            world.module.bank.get(world.actor("examiner"), foreign.id)
        with pytest.raises(NotFound):
            world.module.bank.revise(world.actor("examiner"), foreign.id, content())

    def test_candidates_and_admins_cannot_use_the_bank(self, world):
        for name in ("nora", "admin"):
            with pytest.raises(Forbidden):
                world.module.bank.search(world.actor(name), BankQuery())


class TestAT03EntryAndRoster:
    """AT03 · FR06 (authoring side: enrollment, eligibility, access status)."""

    def published(self, world):
        exam_id, _ = world.three_item_paper()
        actor = world.actor("examiner")
        world.module.roster.enroll(actor, exam_id, ["nora@example.test"])
        world.module.exams.publish(actor, exam_id)
        return exam_id

    def test_only_enrolled_candidate_may_start_inside_window(self, world):
        exam_id = self.published(world)
        nora, eli = world.actor("nora"), world.actor("eli")
        world.clock.current = OPENS - timedelta(minutes=5)
        assert world.module.roster.entry_decision(nora, exam_id).access is Access.UPCOMING
        assert not world.module.roster.entry_decision(nora, exam_id).can_start
        world.clock.current = OPENS + timedelta(minutes=12)  # 10:42
        assert world.module.roster.entry_decision(nora, exam_id).can_start
        with pytest.raises(NotFound):
            world.module.roster.entry_decision(eli, exam_id)

    def test_roster_and_dashboard_show_access_status(self, world):
        exam_id = self.published(world)
        examiner = world.actor("examiner")
        world.module.roster.enroll(examiner, exam_id, ["eli@example.test"])
        nora_id = world.accounts["nora"].id
        world.module.roster.set_active(examiner, exam_id, nora_id, False)
        roster = world.module.roster.roster(examiner, exam_id)
        assert [(r.account.display_name, r.decision.access) for r in roster.entries] == [
            ("Eli Brooks", Access.UPCOMING), ("Nora Khan", Access.ENROLLMENT_INACTIVE)]
        world.clock.current = OPENS + timedelta(minutes=1)
        listed = world.module.roster.assigned_exams(world.actor("eli"))
        assert [(e.exam.id, e.decision.access) for e in listed] == [(exam_id, Access.AVAILABLE)]
        assert world.module.roster.assigned_exams(world.actor("nora")) == []

    def test_draft_exam_is_invisible_to_enrolled_candidate(self, world):
        exam_id, _ = world.three_item_paper()
        world.module.roster.enroll(world.actor("examiner"), exam_id, ["nora@example.test"])
        assert world.module.roster.assigned_exams(world.actor("nora")) == []
        with pytest.raises(NotFound):
            world.module.roster.entry_decision(world.actor("nora"), exam_id)

    def test_enrollment_rejects_non_candidates_and_is_atomic(self, world):
        exam_id, _ = world.three_item_paper()
        examiner = world.actor("examiner")
        with pytest.raises(ValidationFailed) as caught:
            world.module.roster.enroll(examiner, exam_id, [
                "nora@example.test", "ola@example.test", "nobody@example.test",
                "dee@example.test"])
        assert [(i.code, i.row) for i in caught.value.issues] == [
            ("not_candidate", 2), ("unknown_candidate", 3), ("account_disabled", 4)]
        assert world.module.roster.roster(examiner, exam_id).entries == ()

    def test_closed_exam_roster_is_a_record(self, world):
        exam_id = self.published(world)
        world.clock.current = CLOSES
        with pytest.raises(Conflict):
            world.module.roster.enroll(world.actor("examiner"), exam_id, ["eli@example.test"])

    def test_other_examiner_cannot_see_roster(self, world):
        exam_id = self.published(world)
        with pytest.raises(NotFound):
            world.module.roster.roster(world.actor("other"), exam_id)


class TestAT06Sandbox:
    """AT06 · SR03: preview changes no real records and exposes no keys."""

    def test_preview_is_read_only_and_candidate_safe(self, world):
        exam_id, _ = world.three_item_paper()
        before = world.snapshot()
        sandbox = world.module.sandbox.open(world.actor("examiner"), exam_id)
        assert world.snapshot() == before
        assert [i.slot for i in sandbox.items] == [1, 2, 3]
        assert sandbox.deadline_at - sandbox.server_time == timedelta(minutes=30)
        for item in sandbox.items:
            assert not hasattr(item, "correct_option_ids")
            assert all(not hasattr(o, "correct") for o in item.options)

    def test_preview_requires_ownership(self, world):
        exam_id, _ = world.three_item_paper()
        with pytest.raises(NotFound):
            world.module.sandbox.open(world.actor("other"), exam_id)
        with pytest.raises(Forbidden):
            world.module.sandbox.open(world.actor("nora"), exam_id)


class TestExamRegister:
    def test_lists_only_owned_exams_with_state(self, world):
        exam_id, _ = world.three_item_paper()
        world.module.exams.create_draft(world.actor("other"), world.details())
        listed = world.module.exams.list_owned(world.actor("examiner"))
        assert [(s.exam.id, s.state, s.allocated_marks) for s in listed] == [
            (exam_id, ExamState.DRAFT, marks("10"))]

    def test_unknown_exam_is_not_found(self, world):
        with pytest.raises(NotFound):
            world.module.exams.overview(world.actor("examiner"), uuid4())
