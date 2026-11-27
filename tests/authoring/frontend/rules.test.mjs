// Run: node --test tests/authoring/frontend
import { test } from "node:test";
import assert from "node:assert/strict";
import { detailsIssues, parseMarks, questionIssues, reviewPublication, tally, examState } from "../../../frontend/src/features/authoring/domain/rules.js";
import { parseCsv } from "../../../frontend/src/features/authoring/domain/csv.js";

const codes = issues => issues.map(i => i.code).sort();

test("marks parse to exact cents and refuse zero, negatives and extra precision", () => {
  assert.equal(parseMarks("2").cents, 200);
  assert.equal(parseMarks("4.5").cents, 450);
  assert.equal(parseMarks("0.00").issue.code, "non_positive_marks");
  assert.equal(parseMarks("-1").issue.code, "non_positive_marks");
  assert.equal(parseMarks("1.005").issue.code, "marks_precision");
  assert.equal(parseMarks("ten").issue.code, "invalid_marks");
});

test("FR03 particulars report every broken rule", () => {
  const issues = detailsIssues({ title: " ", opens_at: "2026-11-27T10:30:00Z", closes_at: "2026-11-27T10:30:00Z", duration_minutes: 0, total_marks: "0" });
  assert.deepEqual(codes(issues), ["close_before_open", "non_positive_duration", "non_positive_marks", "required"]);
});

test("FR05 key cardinality per kind", () => {
  const base = { topic: "T", prompt: "P", options: [{ id: 1, label: "A" }, { id: 2, label: "B" }] };
  assert.deepEqual(codes(questionIssues({ ...base, kind: "single", marking_rule: "exact", correct_option_ids: [1, 2] })), ["single_key_count"]);
  assert.deepEqual(codes(questionIssues({ ...base, kind: "multiple", marking_rule: "partial_no_wrong", correct_option_ids: [] })), ["multiple_key_count"]);
  assert.deepEqual(codes(questionIssues({ ...base, kind: "written", marking_rule: "manual", correct_option_ids: [] })), ["written_has_options"]);
  assert.deepEqual(questionIssues({ ...base, kind: "single", marking_rule: "exact", correct_option_ids: [2] }), []);
});

test("the ledger tallies slots against the declared total", () => {
  const t = tally([{ slot: 1, max_marks: "2" }, { slot: 2, max_marks: "4" }], "10");
  assert.deepEqual([t.allocated, t.remaining, t.excess, t.balanced], [600, 400, 0, false]);
  const over = tally([{ slot: 1, max_marks: "8" }, { slot: 2, max_marks: "4" }], "10");
  assert.deepEqual([over.excess, over.balanced], [200, false]);
});

test("publication review mirrors the server checklist", () => {
  const version = { topic: "T", prompt: "P", kind: "single", marking_rule: "exact", options: [{ id: 1, label: "A" }, { id: 2, label: "B" }], correct_option_ids: [1] };
  const exam = { title: "Field ecology", opens_at: "2099-01-01T10:30:00Z", closes_at: "2099-01-01T11:00:00Z", duration_minutes: 30, total_marks: "10",
    items: [{ slot: 1, question_id: "a", max_marks: "2", version }, { slot: 2, question_id: "b", max_marks: "4", version }] };
  const report = reviewPublication(exam, new Date("2098-12-31T00:00:00Z"));
  assert.equal(report.ready, false);
  assert.deepEqual(report.checks.filter(c => !c.passed).map(c => c.name), ["total"]);
  exam.items.push({ slot: 3, question_id: "c", max_marks: "4", version });
  assert.equal(reviewPublication(exam, new Date("2098-12-31T00:00:00Z")).ready, true);
  assert.equal(examState({ ...exam, published_at: "x" }, new Date("2099-01-01T10:42:00Z")), "ongoing");
});

test("CSV rows keep their line numbers and quoted JSON", () => {
  const { header, rows } = parseCsv('a,b\n1,"[{""id"":1}]"\n\n"x\ny",2,3\n');
  assert.deepEqual(header, ["a", "b"]);
  assert.deepEqual(rows.map(r => [r.row, r.extra]), [[2, false], [4, true]]);
  assert.equal(rows[0].values.b, '[{"id":1}]');
});
