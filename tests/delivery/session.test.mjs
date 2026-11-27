import assert from "node:assert/strict";
import test from "node:test";
import { AttemptSession } from "../../frontend/src/features/delivery/session.js";

const item = { slot: 9, display_no: 1, kind: "written", written_answer: "", flagged: false, revision: 3 };
function fixture(t, { pending = [], conflicts = {}, fetch }) {
  let cached = {
    paper: { items: [{ ...item }], deadline_at: new Date(Date.now() + 60000).toISOString() },
    pending,
    conflicts,
    offset: 0,
    scratch: "private note",
  };
  const views = [];
  t.mock.method(globalThis, "fetch", fetch);
  const storage = async (_account, _id, update) => {
    cached = update(structuredClone(cached));
    return structuredClone(cached);
  };
  const session = new AttemptSession("candidate", "attempt", (v) => views.push(v), storage);
  return { session, views, cache: () => cached };
}
const response = (body, status = 200) => Response.json(body, { status });
const edit = { slot: 9, id: "pending", base_revision: 3, body: { written_answer: "local", flagged: false } };

test("online resume with revoked access never renders the private cache", async (t) => {
  let release;
  const request = new Promise((resolve) => {
    release = resolve;
  });
  const { session, views, cache } = fixture(t, { fetch: () => request });
  const start = session.init();
  await new Promise((resolve) => setImmediate(resolve));
  assert.ok(views.every((v) => !v.record));
  release(response({ detail: { code: "unavailable" } }, 403));
  await start;
  assert.equal(cache(), undefined);
  assert.ok(views.at(-1).denied);
});

test("unreachable server restores durable edits and labels them local", async (t) => {
  const { session, views } = fixture(t, {
    pending: [edit],
    fetch: async () => {
      throw new TypeError("offline");
    },
  });
  await session.init();
  assert.equal(views.at(-1).record.scratch, "private note");
  assert.equal(views.at(-1).status, "On this device");
});

test("a conflicting answer blocks normal submit and needs an explicit saved-only choice", async (t) => {
  let posts = 0;
  const receipt = {
    attempt_id: "attempt",
    finalized_at: new Date().toISOString(),
    close_reason: "submitted",
  };
  const { session, cache, views } = fixture(t, {
    pending: [edit],
    conflicts: { 9: { ...item, written_answer: "server" } },
    fetch: async (_url, options) =>
      options.method === "POST" ? (posts++, response(receipt)) : response({ ...receipt, items: [item] }),
  });
  session.active = true;
  await session.mutate((value) => value);
  await session.submit();
  assert.equal(posts, 0);
  assert.ok(views.at(-1).submitBlocked);
  assert.equal(cache().pending.length, 1);
  await session.submit({ acceptedOnly: true });
  assert.equal(posts, 1);
  assert.deepEqual(views.at(-1).outstanding, [1]);
  assert.equal(cache(), undefined);
});

test("changing the wall clock after sync does not shorten the displayed exam", async (t) => {
  const start = Date.now();
  const paper = {
    items: [item],
    server_time: new Date(start).toISOString(),
    deadline_at: new Date(start + 60000).toISOString(),
  };
  const { session } = fixture(t, { fetch: async () => response(paper) });
  await session.init();
  t.mock.method(Date, "now", () => start + 7 * 86400000);
  assert.ok(session.timeLeft() > 59000 && session.timeLeft() <= 60000);
});
