import { test } from "node:test";
import assert from "node:assert/strict";
import { versionChanges, wordDiff } from "../../../frontend/src/features/authoring/domain/diff.js";

const text = (parts, op) => parts.filter(p => p.op === op).map(p => p.text.trim()).join("|");

test("word diff marks only the changed words", () => {
  const parts = wordDiff("Which factor is the light level measured in this study?", "Which factor in this study is abiotic?");
  const rebuilt = parts.filter(p => p.op !== "del").map(p => p.text).join("");
  assert.equal(rebuilt, "Which factor in this study is abiotic?");
  assert.ok(text(parts, "same").startsWith("Which"));
  assert.ok(text(parts, "del").includes("light"));
  assert.equal(text(parts, "ins"), "is abiotic");
});

test("version changes match options by ID and report key moves", () => {
  const opt = (id, label, correct = false) => ({ id, label, correct });
  const prev = { topic: "Ecology", difficulty: "easy", kind: "single", marking_rule: "exact", rubric: null, prompt: "P",
    options: [opt(1, "Light", true), opt(2, "Rabbit"), opt(3, "Owl")] };
  const next = { ...prev, difficulty: "medium", options: [opt(1, "Light"), opt(2, "Rabbit", true), opt(4, "Soil pH")] };
  const c = versionChanges(prev, next);
  assert.equal(c.prompt, null);
  assert.deepEqual(c.fields.map(f => [f.key, f.from, f.to]), [["difficulty", "easy", "medium"]]);
  assert.deepEqual(c.options.map(o => [o.id, o.change, o.keyNow]), [[1, "changed", false], [2, "changed", true], [4, "added", undefined], [3, "removed", undefined]]);
  assert.equal(versionChanges(prev, prev).empty, true);
});
