// Planning insights for examiners. Pure functions, mark arithmetic in cents.
import { parseMarks } from "./rules.js";

const MINUTE = 60_000;

/**
 * How the window and duration interact. A start after `lastFullStart` is cut
 * off at closing (FR07: deadline = min(start + duration, close)).
 */
export function windowPlan(opensIso, closesIso, durationMinutes) {
  const opens = Date.parse(opensIso), closes = Date.parse(closesIso), minutes = Number(durationMinutes);
  if (Number.isNaN(opens) || Number.isNaN(closes) || closes <= opens || !(minutes > 0)) return { valid: false };
  const windowMinutes = Math.round((closes - opens) / MINUTE);
  const fullMinutes = Math.max(0, windowMinutes - minutes);
  return {
    valid: true, windowMinutes, durationMinutes: minutes, fullMinutes,
    lastFullStart: new Date(Math.max(opens, closes - minutes * MINUTE)).toISOString(),
    fullShare: fullMinutes / windowMinutes,
    durationExceedsWindow: minutes > windowMinutes,
  };
}

const share = (cents, total) => (total ? cents / total : 0);

function groupBy(items, key, order) {
  const groups = new Map((order ?? []).map(k => [k, { key: k, cents: 0, count: 0 }]));
  for (const item of items) {
    const k = key(item);
    if (!groups.has(k)) groups.set(k, { key: k, cents: 0, count: 0 });
    const g = groups.get(k);
    g.cents += item.cents; g.count += 1;
  }
  return [...groups.values()];
}

/** Distribution of marks across difficulty, type, topic and marking workload. */
export function paperProfile(slots) {
  const items = slots.map(s => ({ ...s.version, cents: parseMarks(s.max_marks).cents ?? 0 }));
  const total = items.reduce((sum, i) => sum + i.cents, 0);
  const withShare = groups => groups.map(g => ({ ...g, share: share(g.cents, total) }));
  const manual = items.filter(i => i.kind === "written").reduce((sum, i) => sum + i.cents, 0);
  return {
    total,
    difficulty: withShare(groupBy(items, i => i.difficulty, ["easy", "medium", "hard"])),
    kind: withShare(groupBy(items, i => i.kind, ["single", "multiple", "written"])),
    topics: withShare(groupBy(items, i => i.topic)).sort((a, b) => b.cents - a.cents || a.key.localeCompare(b.key)),
    automatic: total - manual,
    manual,
  };
}

export const percent = value => `${Math.round(value * 100)}%`;
