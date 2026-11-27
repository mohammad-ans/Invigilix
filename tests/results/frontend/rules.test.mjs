import test from "node:test";
import assert from "node:assert/strict";

import {
  isFeedStale,
  isPdfBytes,
  sha256HexFromBuffer,
  validateAnnouncementInput,
  validateAwardInput,
  validateVerifyInputs,
} from "../../../frontend/src/features/results/domain/rules.js";
import { matchRoute, paths } from "../../../frontend/src/features/results/paths.js";

test("route paths and matcher cover all 5 results screens", () => {
  assert.deepEqual(matchRoute(paths.monitor("ex-1")), { name: "monitor", params: { id: "ex-1" } });
  assert.deepEqual(matchRoute(paths.marking("ex-1")), { name: "marking", params: { id: "ex-1" } });
  assert.deepEqual(matchRoute(paths.results("ex-1")), { name: "results", params: { id: "ex-1" } });
  assert.deepEqual(matchRoute(paths.candidateResult("att-9")), { name: "candidateResult", params: { id: "att-9" } });
  assert.deepEqual(matchRoute(paths.verify), { name: "verify", params: {} });
  assert.equal(matchRoute("/unknown"), null);
});

test("validateAwardInput checks bounds and two-decimal precision", () => {
  assert.deepEqual(validateAwardInput("3", "4.00"), { value: "3.00", cents: 300 });
  assert.deepEqual(validateAwardInput("0.00", "4.00"), { value: "0.00", cents: 0 });
  assert.equal(validateAwardInput("5.00", "4.00").issue.code, "award_out_of_bounds");
  assert.equal(validateAwardInput("-0.1", "4.00").issue.code, "award_out_of_bounds");
  assert.equal(validateAwardInput("1.234", "4.00").issue.code, "too_many_decimals");
  assert.equal(validateAwardInput("", "4.00").issue.code, "required");
});

test("validateAnnouncementInput rejects blank and overly long messages", () => {
  assert.deepEqual(validateAnnouncementInput("  Check units  "), { value: "Check units" });
  assert.equal(validateAnnouncementInput("   ").issue.code, "empty_message");
  assert.equal(validateAnnouncementInput("a".repeat(2001)).issue.code, "message_too_long");
});

test("validateVerifyInputs, PDF header check, and SHA-256 helper", async () => {
  const bytes = new TextEncoder().encode("%PDF-1.4\nsample");
  assert.equal(isPdfBytes(bytes), true);
  assert.equal(isPdfBytes(new TextEncoder().encode("not a pdf")), false);

  const hex = await sha256HexFromBuffer(bytes.buffer);
  assert.match(hex, /^[0-9a-f]{64}$/);
  assert.deepEqual(validateVerifyInputs(" CODE-1 ", hex.toUpperCase()), {
    code: "CODE-1",
    digest: hex,
  });

  const bad = validateVerifyInputs("", "bad");
  assert.equal(bad.issues.length, 2);
});

test("isFeedStale detects feeds older than threshold", () => {
  assert.equal(isFeedStale(1000, 20000, 30000), false);
  assert.equal(isFeedStale(1000, 40000, 30000), true);
});
