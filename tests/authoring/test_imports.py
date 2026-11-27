"""AT10 · SR04 · NFR02: bulk import validates every row and commits atomically."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.features.authoring.domain import Conflict, Forbidden, NotFound, ValidationFailed
from app.features.authoring.ports import BankQuery
from support import CLOSES

Q1, Q2, Q3 = (str(uuid4()) for _ in range(3))
HEADER = "question_id,topic,difficulty,kind,prompt,marking_rule,options,correct_option_ids,rubric\n"


def questions_csv(*rows: str) -> bytes:
    return (HEADER + "".join(r + "\n" for r in rows)).encode()


SINGLE = (f'{Q1},Ecology,easy,single,Which factor is abiotic?,exact,'
          '"[{""id"":1,""label"":""Light""},{""id"":2,""label"":""Rabbit""}]","[1]",')
MULTI = (f'{Q2},Sampling,medium,multiple,Which records make it reproducible?,partial_no_wrong,'
         '"[{""id"":1,""label"":""Quadrat size""},{""id"":2,""label"":""Coordinates""},'
         '{""id"":3,""label"":""Favourite species""}]","[1,2]",')
WRITTEN = (f'{Q3},Sampling,hard,written,Describe one source of sampling bias.,manual,"[]","[]",'
           'Names a concrete bias and its effect.')
BAD_KEY = SINGLE.replace('"[1]"', '"[1,2]"')


def located(error):
    return [(i.row, i.field, i.code) for i in error.value.issues]


class TestQuestionImport:
    def bank(self, world):
        return world.module.bank.search(world.actor("examiner"), BankQuery())

    def test_invalid_row_leaves_zero_changes_then_corrected_file_commits(self, world):
        actor = world.actor("examiner")
        before = world.snapshot()
        with pytest.raises(ValidationFailed) as caught:
            world.module.question_import.run(actor, questions_csv(SINGLE, BAD_KEY.replace(Q1, Q2),
                                                                  WRITTEN), commit=True)
        assert located(caught) == [(3, "correct_option_ids", "single_key_count")]
        assert world.snapshot() == before

        report = world.module.question_import.run(actor, questions_csv(SINGLE, MULTI, WRITTEN),
                                                  commit=True)
        assert (report.created, report.updated, report.unchanged, report.committed) == (
            3, 0, 0, True)
        assert len(self.bank(world)) == 3

    def test_repeated_file_creates_no_duplicates_and_edits_append_versions(self, world):
        actor = world.actor("examiner")
        world.module.question_import.run(actor, questions_csv(SINGLE, MULTI), commit=True)
        again = world.module.question_import.run(actor, questions_csv(SINGLE, MULTI), commit=True)
        assert (again.created, again.updated, again.unchanged) == (0, 0, 2)
        edited = SINGLE.replace("Which factor is abiotic?", "Which factor is non-living?")
        third = world.module.question_import.run(actor, questions_csv(edited, MULTI), commit=True)
        assert (third.created, third.updated, third.unchanged) == (0, 1, 1)
        question, _ = world.module.bank.get(actor, UUID(Q1))
        assert [v.number for v in question.versions] == [1, 2]

    def test_dry_run_reports_without_writing(self, world):
        before = world.snapshot()
        report = world.module.question_import.run(world.actor("examiner"),
                                                  questions_csv(SINGLE, MULTI), commit=False)
        assert (report.created, report.committed, report.issues) == (2, False, [])
        assert world.snapshot() == before

    def test_row_and_field_errors(self, world):
        rows = [
            SINGLE,
            SINGLE,  # duplicate id within the file
            "not-a-uuid,Ecology,easy,single,P,exact,\"[]\",\"[]\",",
            f"{uuid4()},Ecology,trivial,essay,P,exact,\"[]\",\"[]\",",
            f'{uuid4()},Ecology,easy,single,P,exact,"[{{""id"":1,""label"":""A""}},'
            f'{{""id"":2,""label"":""B""}}]","[9]",',
            f'{uuid4()},Ecology,easy,single,P,exact,not json,"[1]",',
        ]
        report = world.module.question_import.run(world.actor("examiner"), questions_csv(*rows),
                                                  commit=False)
        assert [(i.row, i.field, i.code) for i in report.issues] == [
            (3, "question_id", "duplicate_row"),
            (4, "question_id", "invalid_uuid"),
            (5, "difficulty", "invalid_choice"),
            (5, "kind", "invalid_choice"),
            (6, "correct_option_ids", "unknown_key"),
            (7, "options", "invalid_json"),
        ]

    def test_header_and_encoding(self, world):
        actor = world.actor("examiner")
        with pytest.raises(ValidationFailed) as caught:
            world.module.question_import.run(actor, b"question_id,topic,colour\n1,2,3\n",
                                             commit=False)
        fields = {(i.field, i.code) for i in caught.value.issues}
        assert ("prompt", "missing_column") in fields and ("colour", "unknown_column") in fields
        with pytest.raises(ValidationFailed) as caught:
            world.module.question_import.run(actor, HEADER.encode() + b"\xff\xfe\n", commit=False)
        assert located(caught) == [(None, "file", "not_utf8")]
        with pytest.raises(ValidationFailed) as caught:
            world.module.question_import.run(actor, HEADER.encode(), commit=False)
        assert located(caught) == [(None, "file", "empty_file")]

    def test_another_examiners_id_is_refused(self, world):
        world.module.question_import.run(world.actor("other"), questions_csv(SINGLE), commit=True)
        report = world.module.question_import.run(world.actor("examiner"), questions_csv(SINGLE),
                                                  commit=False)
        assert [(i.row, i.code) for i in report.issues] == [(2, "id_in_use")]

    def test_extra_values_are_flagged(self, world):
        report = world.module.question_import.run(world.actor("examiner"),
                                                  questions_csv(SINGLE + ",surplus"), commit=False)
        assert [(i.row, i.code) for i in report.issues] == [(2, "extra_values")]


class TestRosterImport:
    def exam(self, world):
        exam_id, _ = world.three_item_paper()
        return exam_id

    def test_invalid_rows_reported_then_valid_file_commits_once(self, world):
        exam_id, actor = self.exam(world), world.actor("examiner")
        bad = b"candidate_email\nnora@example.test\nola@example.test\nghost@example.test\n"
        with pytest.raises(ValidationFailed) as caught:
            world.module.roster_import.run(actor, bad, commit=True, exam_id=exam_id)
        assert located(caught) == [(3, "candidate_email", "not_candidate"),
                                   (4, "candidate_email", "unknown_candidate")]
        assert world.module.roster.roster(actor, exam_id).entries == ()

        good = b"candidate_email\nnora@example.test\nELI@example.test\n"
        first = world.module.roster_import.run(actor, good, commit=True, exam_id=exam_id)
        second = world.module.roster_import.run(actor, good, commit=True, exam_id=exam_id)
        assert (first.created, second.created, second.unchanged) == (2, 0, 2)
        assert len(world.module.roster.roster(actor, exam_id).entries) == 2

    def test_case_insensitive_duplicate_within_file(self, world):
        report = world.module.roster_import.run(
            world.actor("examiner"), b"candidate_email\nnora@example.test\nNORA@example.test\n",
            commit=False, exam_id=self.exam(world))
        assert [(i.row, i.code) for i in report.issues] == [(3, "duplicate_row")]

    def test_scope_is_the_owned_open_exam(self, world):
        exam_id = self.exam(world)
        with pytest.raises(NotFound):
            world.module.roster_import.run(world.actor("other"), b"candidate_email\nx@y.z\n",
                                           commit=False, exam_id=exam_id)
        world.module.exams.publish(world.actor("examiner"), exam_id)
        world.clock.current = CLOSES
        with pytest.raises(Conflict):
            world.module.roster_import.run(world.actor("examiner"),
                                           b"candidate_email\nnora@example.test\n",
                                           commit=True, exam_id=exam_id)


class TestCandidateImport:
    def test_admin_imports_candidates_and_receives_credentials_once(self, world):
        admin = world.actor("admin")
        data = "email,display_name\nsana@example.test,Sana Ali\nnora@example.test,Nora Khan\n"
        report = world.module.candidate_import.run(admin, data.encode(), commit=True)
        assert (report.created, report.unchanged) == (1, 1)
        assert [email for email, _ in report.credentials] == ["sana@example.test"]
        assert len(report.credentials[0][1]) >= 16
        again = world.module.candidate_import.run(admin, data.encode(), commit=True)
        assert (again.created, again.unchanged, again.credentials) == (0, 2, [])

    def test_invalid_rows(self, world):
        data = ("email,display_name\nnot-an-email,X\nremy@example.test,Remy\n"
                "new@example.test,\n").encode()
        report = world.module.candidate_import.run(world.actor("admin"), data, commit=False)
        assert [(i.row, i.field, i.code) for i in report.issues] == [
            (2, "email", "invalid_email"), (3, "email", "email_in_use"),
            (4, "display_name", "required")]

    def test_only_admins(self, world):
        with pytest.raises(Forbidden):
            world.module.candidate_import.run(world.actor("examiner"),
                                              b"email,display_name\na@b.c,A\n", commit=False)
