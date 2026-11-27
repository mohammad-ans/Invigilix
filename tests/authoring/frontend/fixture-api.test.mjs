// The preview adapter must honour the same contract as the FastAPI router.
import { test } from "node:test";
import assert from "node:assert/strict";
import { FixtureAuthoringApi } from "../../../frontend/src/features/authoring/api/FixtureAuthoringApi.js";

const api = () => new FixtureAuthoringApi({ latency: 0 });
const rejects = async (promise, status, code) => {
  await assert.rejects(promise, e => e.status === status && e.code === code);
};

test("seed register covers every exam state", async () => {
  const states = (await api().listExams()).map(e => e.state).sort();
  assert.deepEqual(states, ["completed", "draft", "draft", "ongoing", "scheduled"]);
});

test("AT02: invalid total cannot publish; fixed total publishes and freezes", async () => {
  const a = api();
  const soil = (await a.listExams()).find(e => e.title === "Soil chemistry");
  await rejects(a.publishExam(soil.id), 422, "paper_invalid");
  const exam = await a.getExam(soil.id);
  await a.updateExam(soil.id, { ...exam, total_marks: "12" });
  const published = await a.publishExam(soil.id);
  assert.equal(published.state, "scheduled");
  await rejects(a.updateExam(soil.id, exam), 409, "exam_published");
});

test("AT02: editing a bank item keeps the frozen version on the paper", async () => {
  const a = api();
  const live = (await a.listExams()).find(e => e.state === "ongoing");
  const before = await a.getExam(live.id);
  const slot = before.items[0];
  const { latest } = (await a.searchQuestions()).find(q => q.id === slot.question_id);
  const revised = await a.reviseQuestion(slot.question_id, { ...latest, prompt: "Edited after publication" });
  assert.equal(revised.created, true);
  const after = await a.getExam(live.id);
  assert.equal(after.items[0].version.prompt, slot.version.prompt);
  assert.equal(after.items[0].outdated, true);
});

test("AT06: preview omits keys and rubrics", async () => {
  const a = api();
  const draft = (await a.listExams()).find(e => e.title === "Field ecology");
  const paper = await a.previewExam(draft.id);
  const text = JSON.stringify(paper);
  assert.equal(paper.mode, "sandbox");
  for (const secret of ['"correct"', "correct_option_ids", "rubric", "marking_rule"]) assert.ok(!text.includes(secret), secret);
});

test("AT10: an invalid row is located and leaves zero changes", async () => {
  const a = api();
  const draft = (await a.listExams()).find(e => e.title === "Field ecology");
  const before = (await a.getRoster(draft.id)).entries.length;
  const csv = "candidate_email\ntomas.reyes@example.test\nola.examiner@example.test\n";
  const checked = await a.importRoster(draft.id, csv, { dryRun: true });
  assert.deepEqual(checked.issues.map(i => [i.row, i.field, i.code]), [[3, "candidate_email", "not_candidate"]]);
  await rejects(a.importRoster(draft.id, csv), 422, "import_invalid");
  assert.equal((await a.getRoster(draft.id)).entries.length, before);
  const ok = await a.importRoster(draft.id, "candidate_email\ntomas.reyes@example.test\n");
  assert.deepEqual([ok.created, ok.committed], [1, true]);
  const again = await a.importRoster(draft.id, "candidate_email\ntomas.reyes@example.test\n");
  assert.deepEqual([again.created, again.unchanged], [0, 1]);
});

test("AT03: roster distinguishes access states", async () => {
  const a = api();
  const draft = (await a.listExams()).find(e => e.title === "Field ecology");
  const access = (await a.getRoster(draft.id)).entries.map(e => e.access);
  assert.deepEqual(access, ["awaiting_publication", "awaiting_publication", "enrollment_inactive"]);
  await rejects(a.enroll(draft.id, ["dee.lund@example.test"]), 422, "validation_failed");
});

test("copy to new draft keeps pins and leaves the frozen original alone", async () => {
  const a = api();
  const frozen = (await a.listExams()).find(e => e.title === "Ecology mid-term");
  const copy = await a.duplicateExam(frozen.id);
  const original = await a.getExam(frozen.id);
  assert.equal(copy.state, "draft");
  assert.equal(copy.title, "Copy of Ecology mid-term");
  assert.deepEqual(copy.items.map(i => i.version.id), original.items.map(i => i.version.id));
  assert.equal(original.state, "scheduled");
  assert.equal((await a.getRoster(copy.id)).entries.length, 0);
});
