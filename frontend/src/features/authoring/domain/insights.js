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

const DAY = 864e5;

/**
 * Exam timetable rows for `days` days from the start of `now`'s day.
 * Each row places the window as left/width percentages and notes clipping.
 */
export function timetable(exams, now = new Date(), days = 14) {
  const start = new Date(now); start.setHours(0, 0, 0, 0);
  const from = start.getTime(), to = from + days * DAY, span = to - from;
  const rows = exams
    .map(e => ({ exam: e, opens: Date.parse(e.opens_at), closes: Date.parse(e.closes_at) }))
    .filter(r => r.closes > from && r.opens < to)
    .sort((a, b) => a.opens - b.opens)
    .map(r => {
      const a = Math.max(r.opens, from), b = Math.min(r.closes, to);
      return { ...r, left: (100 * (a - from)) / span, width: (100 * (b - a)) / span,
        clippedStart: r.opens < from, clippedEnd: r.closes > to };
    });
  const columns = Array.from({ length: days }, (_, i) => {
    const d = new Date(from + i * DAY);
    return { date: d, weekend: d.getDay() === 0 || d.getDay() === 6, today: i === 0 };
  });
  return { rows, columns, nowLeft: (100 * (now.getTime() - from)) / span, hidden: exams.length - rows.length };
}
