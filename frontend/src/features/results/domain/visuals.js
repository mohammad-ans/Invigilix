// Pure helpers behind the results instruments (seating plan, red-pen marking,
// score strip, verification stub). No DOM; covered by node tests.

/** Quick-mark values for a cap: whole marks, plus halves when the cap is small. */
export function markSteps(cap) {
  const max = Number(cap);
  if (!(max > 0)) return [];
  const step = max <= 3 ? 0.5 : max <= 12 ? 1 : max / 8;
  const out = [];
  for (let v = 0; v <= max + 1e-9; v += step) out.push(Number(v.toFixed(2)));
  if (out[out.length - 1] !== max) out.push(Number(max.toFixed(2)));
  return out;
}

/** Dot positions for a dot plot: equal scores stack upward instead of overlapping. */
export function stackScores(entries, total) {
  const max = Number(total) || 1;
  const levels = new Map();
  return entries
    .filter(e => e.score !== null && e.score !== undefined && e.score !== "")
    .map(e => ({ label: e.label, score: Number(e.score) }))
    .sort((a, b) => a.score - b.score)
    .map(e => {
      const key = e.score.toFixed(2);
      const level = levels.get(key) ?? 0;
      levels.set(key, level + 1);
      return { ...e, level, fraction: Math.min(Math.max(e.score / max, 0), 1) };
    });
}

/** Axis ticks for a 0..total rule: every mark up to 20, otherwise tenths. */
export function axisTicks(total) {
  const max = Number(total);
  if (!(max > 0)) return [0];
  const step = max <= 20 ? 1 : max / 10;
  const ticks = [];
  for (let v = 0; v <= max + 1e-9; v += step) ticks.push(Number(v.toFixed(2)));
  return ticks;
}

/** Split a hex digest into four-character groups for comparison by eye. */
export const digestGroups = hex => String(hex ?? "").match(/.{1,4}/g) ?? [];

/** Answer-sheet pips for a desk tile: filled for answered, open for the rest. */
export const pips = (answered, total) => Array.from({ length: Math.max(0, Number(total) || 0) }, (_, i) => i < answered);

/**
 * Time left on an attempt, judged by the server's clock (IN02: a client clock
 * never extends a deadline). serverIso is the snapshot's server_time; the
 * browser only measures how long ago that snapshot arrived.
 */
export function remainingMs(deadlineIso, serverIso, syncedAtMs, nowMs = Date.now()) {
  if (!deadlineIso || !serverIso || !syncedAtMs) return null;
  const serverNow = Date.parse(serverIso) + Math.max(0, nowMs - syncedAtMs);
  return Date.parse(deadlineIso) - serverNow;
}

export function formatRemaining(ms) {
  if (ms === null || ms === undefined) return null;
  if (ms <= 0) return "time up";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 1) return "under a minute left";
  if (minutes < 60) return `${minutes} min left`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min left`;
}

/** Stable anonymous labels for blind marking: one per attempt, by attempt ID. */
export function scriptLabels(items) {
  const ids = [...new Set(items.map(it => it.attempt_id))].sort();
  const label = n => (n < 26 ? String.fromCharCode(65 + n) : `${String.fromCharCode(65 + Math.floor(n / 26) - 1)}${String.fromCharCode(65 + (n % 26))}`);
  return new Map(ids.map((id, n) => [id, `Script ${label(n)}`]));
}

export const markingProgress = items => ({ done: items.filter(it => it.awarded_marks !== null).length, total: items.length });
