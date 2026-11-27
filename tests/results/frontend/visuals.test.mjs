import { test } from "node:test";
import assert from "node:assert/strict";
import { axisTicks, digestGroups, markSteps, pips, stackScores } from "../../../frontend/src/features/results/domain/visuals.js";

test("quick marks: halves for small caps, whole marks otherwise", () => {
  assert.deepEqual(markSteps(2), [0, 0.5, 1, 1.5, 2]);
  assert.deepEqual(markSteps("4.00"), [0, 1, 2, 3, 4]);
  assert.deepEqual(markSteps(0), []);
  assert.equal(markSteps(20).at(-1), 20);
});

test("equal scores stack instead of overlapping; pending scores are not plotted", () => {
  const dots = stackScores([{ score: "7.00", label: "Sana" }, { score: null, label: "Eli" }, { score: "7.00", label: "Nora" }, { score: "4.00", label: "Remy" }], "10.00");
  assert.deepEqual(dots.map(d => [d.label, d.level, d.fraction]), [["Remy", 0, 0.4], ["Sana", 0, 0.7], ["Nora", 1, 0.7]]);
});

test("axis ticks, digest groups and desk pips", () => {
  assert.equal(axisTicks(10).length, 11);
  assert.equal(axisTicks(50).length, 11);
  assert.deepEqual(digestGroups("66bc4f73eb56"), ["66bc", "4f73", "eb56"]);
  assert.equal(digestGroups("a".repeat(64)).length, 16);
  assert.deepEqual(pips(3, 5), [true, true, true, false, false]);
});
