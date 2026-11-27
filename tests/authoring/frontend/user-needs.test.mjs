// Logic behind the features that came out of the persona walkthroughs.
import { test } from "node:test";
import assert from "node:assert/strict";
import { balanceOptions } from "../../../frontend/src/features/authoring/domain/rules.js";
import { attentionItems } from "../../../frontend/src/features/authoring/domain/insights.js";
import { parseEmailList, usable } from "../../../frontend/src/features/authoring/domain/emails.js";

const slots = caps => caps.map((m, i) => ({ slot: i + 1, max_marks: m }));

test("balance: under-allocated offers 'declare what is allocated' and 'put the gap on the last slot'", () => {
  assert.deepEqual(balanceOptions(slots(["4", "8"]), "20"), [
    { kind: "set_total", cents: 1200 },
    { kind: "adjust_slot", slot: 2, fromCents: 800, toCents: 1600 },
  ]);
});

test("balance: over-allocated trims the largest slot when it can; balanced offers nothing", () => {
  assert.deepEqual(balanceOptions(slots(["2", "6", "4"]), "10"), [
    { kind: "set_total", cents: 1200 },
    { kind: "adjust_slot", slot: 2, fromCents: 600, toCents: 400 },
  ]);
  assert.deepEqual(balanceOptions(slots(["2", "4", "4"]), "10"), []);
  assert.deepEqual(balanceOptions([], "10"), []);
});

test("in-tray: urgent drafts first, then blockers, then information", () => {
  const now = new Date("2026-11-27T12:00:00Z");
  const exam = (id, state, opensInH, extra = {}) => ({ id, title: id, state, item_count: 3, allocated_marks: "10.00", total_marks: "10.00", enrolled: 2,
    opens_at: new Date(now.getTime() + opensInH * 36e5).toISOString(), closes_at: new Date(now.getTime() + (opensInH + 1) * 36e5).toISOString(), ...extra });
  const notes = attentionItems([
    exam("soon", "draft", 20),
    exam("unbalanced", "draft", 200, { allocated_marks: "12.00", total_marks: "20.00" }),
    exam("empty-roster", "scheduled", 100, { enrolled: 0 }),
    exam("ready", "draft", 300),
    exam("live", "ongoing", -0.5),
  ], now);
  assert.deepEqual(notes.map(n => [n.examId, n.tone]), [
    ["soon", "urgent"], ["empty-roster", "action"], ["unbalanced", "action"], ["live", "info"], ["ready", "info"],
  ]);
  assert.equal(notes[0].title, "Opens in 20 hours, still a draft");
  assert.equal(notes.find(n => n.examId === "empty-roster").action.route, "enrollment");
});

test("pasted emails are read live: malformed and repeated entries are named, the rest usable", () => {
  const tokens = parseEmailList("tomas.reyes@example.test, ivy.okafor@example.test;\nivy.okafor@exampletest  IVY.okafor@example.test");
  assert.deepEqual(tokens.map(t => t.status), ["ok", "ok", "malformed", "repeat"]);
  assert.deepEqual(usable(tokens), ["tomas.reyes@example.test", "ivy.okafor@example.test"]);
});
