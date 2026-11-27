import test from "node:test";
import assert from "node:assert/strict";
import { accept, enqueue, resolveConflict, visibleItem } from "../../frontend/src/features/delivery/queue.js";

test("acknowledgments advance dependent edits without rebasing independent stale drafts", () => {
  const first = { slot: 1, kind: "written", written_answer: "", revision: 4, flagged: false };
  const record = { paper: { items: [{ ...first }] }, pending: [], conflicts: {} };
  const body = text => ({ written_answer: text, flagged: true });
  enqueue(record, first, body("First"), "one");
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
