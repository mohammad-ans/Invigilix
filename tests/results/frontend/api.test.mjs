import test from "node:test";
import assert from "node:assert/strict";

import { FixtureResultsApi, SAMPLE_VERIFICATION_CODE } from "../../../frontend/src/features/results/api/FixtureResultsApi.js";
import { ApiError, HttpResultsApi } from "../../../frontend/src/features/results/api/HttpResultsApi.js";
import { sha256HexFromBuffer } from "../../../frontend/src/features/results/domain/rules.js";

test("FixtureResultsApi supports AT06-AT09 workflows in preview mode", async () => {
  const api = new FixtureResultsApi();
  assert.equal(api.mode, "preview");

  // Monitor & announcement (AT06)
  const mon = await api.getMonitor("exam-bio-204");
  assert.equal(mon.counts.enrolled, 4);
  const ann = await api.postAnnouncement("exam-bio-204", "Keep eyes on Q3.");
  assert.equal(ann.message, "Keep eyes on Q3.");

  // Early release blocked until written grade is recorded (AT07)
  await assert.rejects(() => api.publishResults("exam-bio-204"), err => err.status === 409 && err.code === "grading_incomplete");

  // Invalid award rejected with 422
  await assert.rejects(() => api.gradeWrittenItem("att-sana", 3, "5.00"), err => err.status === 422);

  // Award 3/4 -> total 7.00, then release succeeds
  const graded = await api.gradeWrittenItem("att-sana", 3, "3.00");
  assert.equal(graded.attempt_total_score, "7.00");

  const released = await api.publishResults("exam-bio-204");
  assert.ok(released.results_published_at);

  // Candidate result & PDF download + verification (AT09)
  const cand = await api.getCandidateResult("att-sana-released");
  assert.equal(cand.total_score, "7.00");
  assert.equal(cand.max_marks, "10.00");
  const dl = await api.downloadCandidateReport("att-sana-released");
  const bytes = await dl.blob.arrayBuffer();
  const hex = await sha256HexFromBuffer(bytes);
  assert.deepEqual(await api.verifyReport(SAMPLE_VERIFICATION_CODE, hex), { valid: true });
  assert.deepEqual(await api.verifyReport(SAMPLE_VERIFICATION_CODE, "0".repeat(64)), { valid: false });

  // Empty & zero-exposure state (AT08)
  const emptyRes = await api.getExamResults("exam-empty");
  assert.equal(emptyRes.question_analytics[0].skip_rate_display, "No data");
  assert.equal(emptyRes.question_analytics[0].facility_display, "No data");
});

test("HttpResultsApi builds expected requests, handles CSRF and error bodies", async () => {
  const calls = [];
  const mockFetch = async (url, init) => {
    calls.push({ url: String(url), init });
    if (String(url).endsWith("/reports/verify")) {
      return new Response(JSON.stringify({ valid: true }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(
      JSON.stringify({ error: { code: "exam_not_closed", message: "Too early.", issues: [] } }),
      { status: 409, headers: { "Content-Type": "application/json" } }
    );
  };

  const api = new HttpResultsApi({
    baseUrl: "http://localhost:8000/api",
    fetchImpl: mockFetch,
    csrfHeader: () => ({ "X-CSRF-Token": "csrf-xyz" }),
  });

  const v = await api.verifyReport("CODE", "a".repeat(64));
  assert.deepEqual(v, { valid: true });
  assert.equal(calls[0].init.credentials, "omit");

  await assert.rejects(
    () => api.publishResults("exam-1"),
    err => err instanceof ApiError && err.status === 409 && err.code === "exam_not_closed"
  );
  assert.equal(calls[1].init.headers["X-CSRF-Token"], "csrf-xyz");
  assert.equal(calls[1].init.credentials, "same-origin");
  assert.equal(calls[1].init.cache, "no-store");
});
