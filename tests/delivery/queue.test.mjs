import test from "node:test";
import assert from "node:assert/strict";
import { accept, enqueue, resolveConflict, visibleItem } from "../../frontend/src/features/delivery/queue.js";

test("acknowledgments advance dependent edits without rebasing independent stale drafts", () => {
  const first = { slot: 1, kind: "written", written_answer: "", revision: 4, flagged: false };
  const record = { paper: { items: [{ ...first }] }, pending: [], conflicts: {} };
  const body = text => ({ written_answer: text, flagged: true });
  enqueue(record, first, body("First"), "one");
  record.pending[0].dispatched = true;
  enqueue(record, visibleItem(record, 1), body("Next"), "two");
  enqueue(record, first, body("Independent"), "three");
  accept(record, record.pending[0], { revision: 5 });
  assert.deepEqual(record.pending.map(e => e.base_revision), [5, 4]);
  accept(record, record.pending[0], { revision: 6 });
  record.conflicts[1] = { ...first, revision: 7, written_answer: "Another device" };
  assert.equal(visibleItem(record, 1).written_answer, "Independent");
  resolveConflict(record, 1, true);
  assert.equal(record.pending[0].base_revision, 7);
  assert.equal(record.pending[0].body.written_answer, "Independent");
  record.conflicts[1] = { ...first, revision: 8, written_answer: "Server wins" };
  resolveConflict(record, 1, false);
  assert.equal(record.pending.length, 0);
  assert.equal(visibleItem(record, 1).written_answer, "Server wins");
});

test("offline typing coalesces unsent drafts and preserves the body of a dispatched revision", () => {
  const original = { slot: 2, kind: "written", written_answer: "", revision: 7, flagged: false };
  const record = { paper: { items: [{...original}] }, pending: [], conflicts: {} };
  for (let n = 1; n <= 100; n++) {
    enqueue(record, visibleItem(record, 2), { written_answer: "x".repeat(n), flagged: false }, String(n));
  }
  assert.equal(record.pending.length, 1);
  const sent = record.pending[0];
  sent.dispatched = true;
  enqueue(record, visibleItem(record,2), {written_answer: "final", flagged:true}, "101");
  assert.equal(record.pending.length,2);
  assert.equal(sent.body.written_answer.length,100);
  accept(record, sent, {revision:8});
  assert.equal(record.pending[0].base_revision,8);
  assert.equal(visibleItem(record,2).written_answer,"final");
});
