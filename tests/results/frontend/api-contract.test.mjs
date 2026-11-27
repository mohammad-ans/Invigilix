// Liskov check: both results adapters implement exactly the ResultsApi
// interface, and the HTTP adapter keeps its transport private.
import { test } from "node:test";
import assert from "node:assert/strict";
import { RESULTS_API_METHODS, ResultsApi } from "../../../frontend/src/features/results/api/ResultsApi.js";
import { ApiError, HttpResultsApi } from "../../../frontend/src/features/results/api/HttpResultsApi.js";
import { FixtureResultsApi, SAMPLE_VERIFICATION_CODE } from "../../../frontend/src/features/results/api/FixtureResultsApi.js";

const publicMethods = cls => Object.getOwnPropertyNames(cls.prototype)
  .filter(n => n !== "constructor" && n !== "mode" && typeof Object.getOwnPropertyDescriptor(cls.prototype, n).value === "function")
  .sort();

test("both adapters implement exactly the interface and declare a mode", () => {
  const expected = [...RESULTS_API_METHODS].sort();
  assert.deepEqual(publicMethods(HttpResultsApi), expected);
  assert.deepEqual(publicMethods(FixtureResultsApi), expected);
  assert.equal(new FixtureResultsApi().mode, "preview");
  assert.equal(new HttpResultsApi({ fetchImpl: async () => ({}) }).mode, "live");
  assert.ok(new HttpResultsApi() instanceof ResultsApi && new FixtureResultsApi() instanceof ResultsApi);
  assert.equal(Object.keys(new HttpResultsApi()).length, 0, "no public fields leak configuration");
});

test("the base class refuses unimplemented methods", async () => {
  await assert.rejects(new ResultsApi().getMonitor("x"), /not implemented/);
});

test("HTTP verify posts the contract body without credentials leaking into errors", async () => {
  const calls = [];
  const api = new HttpResultsApi({
    csrfHeader: () => ({ "X-CSRF-Token": "t0k" }),
    fetchImpl: async (url, init) => {
      calls.push({ url, ...init });
      return { ok: false, status: 422, headers: { get: () => "application/json" },
        json: async () => ({ error: { code: "validation_failed", message: "Bad.", issues: [{ field: "sha256_hex" }] } }) };
    },
  });
  await assert.rejects(api.verifyReport(SAMPLE_VERIFICATION_CODE, "00"), e => e instanceof ApiError && e.status === 422 && e.issues[0].field === "sha256_hex");
  assert.equal(calls[0].url, "/api/reports/verify");
  assert.equal(calls[0].method, "POST");
  assert.deepEqual(JSON.parse(calls[0].body), { verification_code: SAMPLE_VERIFICATION_CODE, sha256_hex: "00" });
});
