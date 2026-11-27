// Client-side validation, formatting, and PDF digest helpers for results.
// FastAPI stays authoritative; these mirror backend bounds and states cleanly.

export const MAX_ANNOUNCEMENT_LEN = 2000;
export const SHA256_HEX_RE = /^[0-9a-f]{64}$/;
export const STALE_FEED_MS = 30_000;

export function validateAwardInput(raw, maxMarks) {
  const text = String(raw ?? "").trim();
  if (!text) {
    return { issue: { code: "required", message: "Enter a mark award.", field: "awarded_marks" } };
  }
  if (!/^-?\d+(\.\d+)?$/.test(text)) {
    return { issue: { code: "invalid_marks", message: "Enter marks as a decimal number.", field: "awarded_marks" } };
  }
  const [whole, frac = ""] = text.replace(/^-/, "").split(".");
  if (frac.length > 2) {
    return { issue: { code: "too_many_decimals", message: "Use at most two decimal places.", field: "awarded_marks" } };
  }
  const num = Number(text);
  const cap = Number(maxMarks);
  if (!Number.isFinite(num) || num < 0 || num > cap) {
    return {
      issue: {
        code: "award_out_of_bounds",
        message: `Awarded marks must be between 0.00 and ${cap.toFixed(2)}.`,
        field: "awarded_marks",
      },
    };
  }
  return { value: num.toFixed(2), cents: Math.round(num * 100) };
}

export function validateAnnouncementInput(raw) {
  const cleaned = String(raw ?? "").trim();
  if (!cleaned) {
    return { issue: { code: "empty_message", message: "Announcement message cannot be blank.", field: "message" } };
  }
  if (cleaned.length > MAX_ANNOUNCEMENT_LEN) {
    return {
      issue: {
        code: "message_too_long",
        message: `Announcement must be at most ${MAX_ANNOUNCEMENT_LEN} characters.`,
        field: "message",
      },
    };
  }
  return { value: cleaned };
}

export function validateVerifyInputs(verificationCode, sha256Hex) {
  const issues = [];
  const code = String(verificationCode ?? "").trim();
  const digest = String(sha256Hex ?? "").trim().toLowerCase();
  if (!code) {
    issues.push({ code: "empty_code", message: "Enter the verification code printed on the report.", field: "verification_code" });
  }
  if (!SHA256_HEX_RE.test(digest)) {
    issues.push({ code: "invalid_digest", message: "Provide a valid 64-character SHA-256 hex digest or choose a PDF file.", field: "sha256_hex" });
  }
  return issues.length ? { issues } : { code, digest };
}

export function isPdfBytes(bytes) {
  if (!bytes || bytes.length < 5) return false;
  return bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46 && bytes[4] === 0x2d;
}

export async function sha256HexFromBuffer(arrayBuffer) {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", arrayBuffer);
  return Array.from(new Uint8Array(digest))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
}

export function isFeedStale(lastSyncedAtMs, nowMs = Date.now(), thresholdMs = STALE_FEED_MS) {
  if (!lastSyncedAtMs) return false;
  return nowMs - lastSyncedAtMs > thresholdMs;
}

export function formatMarks(value) {
  if (value === null || value === undefined || value === "") return "Pending";
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(2) : String(value);
}

export function formatTime(iso) {
  if (!iso) return "—";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return String(iso);
  return dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatDateTime(iso) {
  if (!iso) return "—";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return String(iso);
  return dt.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export const ATTEMPT_STATUS_META = {
  not_started: { label: "Not started", tone: "muted", glyph: "○" },
  working: { label: "Working", tone: "sage", glyph: "●" },
  reconnected: { label: "Reconnected", tone: "amber", glyph: "↻" },
  submitted: { label: "Submitted", tone: "sage", glyph: "✓" },
  expired: { label: "Expired", tone: "muted", glyph: "◷" },
};

export const EXAM_STATUS_LABEL = {
  draft: "Draft",
  scheduled: "Scheduled",
  ongoing: "Ongoing",
  closed: "Closed",
  results_released: "Results released",
};
