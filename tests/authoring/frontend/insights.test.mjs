import { test } from "node:test";
import assert from "node:assert/strict";
import { paperProfile, windowPlan } from "../../../frontend/src/features/authoring/domain/insights.js";

test("AT03 window: a 30 minute exam in a 30 minute window has no late full-length start", () => {
  const plan = windowPlan("2026-11-27T10:30:00Z", "2026-11-27T11:00:00Z", 30);
  assert.deepEqual([plan.windowMinutes, plan.fullMinutes, plan.lastFullStart], [30, 0, "2026-11-27T10:30:00.000Z"]);
});

test("a wider window leaves time for full-length late starts", () => {
  const plan = windowPlan("2026-11-27T10:00:00Z", "2026-11-27T12:00:00Z", 45);
  assert.deepEqual([plan.fullMinutes, plan.lastFullStart, plan.fullShare], [75, "2026-11-27T11:15:00.000Z", 0.625]);
  assert.equal(windowPlan("2026-11-27T10:00:00Z", "2026-11-27T10:20:00Z", 45).durationExceedsWindow, true);
  assert.equal(windowPlan("x", "y", 30).valid, false);
});

test("profile weights by marks and splits automatic from examiner marking", () => {
  const v = (kind, difficulty, topic) => ({ kind, difficulty, topic });
  const p = paperProfile([
    { max_marks: "2", version: v("single", "easy", "Ecology") },
    { max_marks: "4", version: v("multiple", "medium", "Sampling") },
    { max_marks: "4", version: v("written", "hard", "Sampling") },
  ]);
  assert.deepEqual([p.total, p.automatic, p.manual], [1000, 600, 400]);
  assert.deepEqual(p.difficulty.map(g => g.share), [0.2, 0.4, 0.4]);
  assert.deepEqual(p.topics.map(t => [t.key, t.share]), [["Sampling", 0.8], ["Ecology", 0.2]]);
});
