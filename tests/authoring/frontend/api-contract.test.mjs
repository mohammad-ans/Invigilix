// Liskov check: both adapters implement exactly the AuthoringApi interface,
// and the HTTP adapter maps the contract onto the real paths and errors.
import { test } from "node:test";
import assert from "node:assert/strict";
import { AUTHORING_API_METHODS, AuthoringApi } from "../../../frontend/src/features/authoring/api/AuthoringApi.js";
import { ApiError, HttpAuthoringApi } from "../../../frontend/src/features/authoring/api/HttpAuthoringApi.js";
import { FixtureAuthoringApi } from "../../../frontend/src/features/authoring/api/FixtureAuthoringApi.js";

const publicMethods = cls => Object.getOwnPropertyNames(cls.prototype)
  .filter(n => n !== "constructor" && n !== "mode" && typeof Object.getOwnPropertyDescriptor(cls.prototype, n).value === "function")
  .sort();

test("both adapters implement exactly the interface and declare a mode", () => {
  const expected = [...AUTHORING_API_METHODS].sort();
  assert.deepEqual(publicMethods(HttpAuthoringApi), expected);
  assert.deepEqual(publicMethods(FixtureAuthoringApi), expected);
  assert.equal(new FixtureAuthoringApi({ latency: 0 }).mode, "preview");
  assert.equal(new HttpAuthoringApi({ fetchImpl: async () => ({}) }).mode, "live");
  assert.ok(new HttpAuthoringApi() instanceof AuthoringApi);
});

test("the base class refuses unimplemented methods", async () => {
  await assert.rejects(new AuthoringApi().listExams(), /not implemented/);
});

test("HTTP adapter uses the contract paths, CSRF on writes, and typed errors", async () => {
  globalThis.window = { location: { origin: "https://folio.example" } };
  const calls = [];
  const reply = (status, body) => ({ ok: status < 400, status, json: async () => body });
  const api = new HttpAuthoringApi({
    baseUrl: "/api/",
    csrfHeader: () => ({ "X-CSRF-Token": "t0k" }),
    fetchImpl: async (url, init) => {
      calls.push({ url: String(url), ...init });
      if (String(url).endsWith("/publish")) {
        return reply(422, { error: { code: "paper_invalid", message: "No.", issues: [{ code: "total_mismatch", field: "total_marks" }] } });
      }
      return reply(200, []);
    },
  });
  await api.searchQuestions({ topic: "Ecology", q: "" });
  await api.importRoster("e1", "candidate_email\n", { dryRun: true });
  await assert.rejects(api.publishExam("e1"), e => e instanceof ApiError && e.status === 422
    && e.code === "paper_invalid" && e.isValidation && e.issues[0].field === "total_marks");
  assert.equal(calls[0].url, "https://folio.example/api/questions?topic=Ecology");
  assert.equal(calls[0].headers["X-CSRF-Token"], undefined);
  assert.equal(calls[1].url, "https://folio.example/api/exams/e1/enrollments/import?dry_run=true");
  assert.equal(calls[1].headers["Content-Type"], "text/csv; charset=utf-8");
  assert.equal(calls[1].headers["X-CSRF-Token"], "t0k");
  assert.equal(calls[2].method, "POST");
  assert.equal(calls[2].cache, "no-store");
});

test("network failure becomes a typed error, not an exception leak", async () => {
  globalThis.window = { location: { origin: "https://folio.example" } };
  const api = new HttpAuthoringApi({ fetchImpl: async () => { throw new TypeError("offline"); } });
  await assert.rejects(api.listExams(), e => e instanceof ApiError && e.status === 0 && e.code === "network");
});
