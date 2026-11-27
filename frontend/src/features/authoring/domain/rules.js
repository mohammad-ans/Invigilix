// Client-side mirror of the authoring rules (FR03–FR05). FastAPI stays
// authoritative; these give instant, field-level feedback before a request
// and power the fixture adapter. Issue shape matches the API:
// { code, message, field?, item?, row? }.

export const KINDS = ["single", "multiple", "written"];
export const DIFFICULTIES = ["easy", "medium", "hard"];
export const RULES_FOR_KIND = {
  single: ["exact"],
  multiple: ["exact", "partial_no_wrong"],
  written: ["manual"],
};

const issue = (code, message, where = {}) => ({ code, message, ...where });

/** Parse a positive mark value with at most two decimals into integer cents. */
export function parseMarks(value, field = "max_marks") {
  const text = String(value ?? "").trim();
  if (!/^\d+(\.\d+)?$/.test(text)) {
    if (/^-/.test(text) || text === "0") return { issue: issue("non_positive_marks", "Marks must be greater than zero.", { field }) };
    return { issue: issue("invalid_marks", "Enter marks as a number.", { field }) };
  }
  const [whole, fraction = ""] = text.split(".");
  if (fraction.length > 2) return { issue: issue("marks_precision", "Use at most two decimal places.", { field }) };
  const cents = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  if (cents <= 0) return { issue: issue("non_positive_marks", "Marks must be greater than zero.", { field }) };
  if (cents > 99999999) return { issue: issue("marks_too_large", "Marks exceed the supported maximum.", { field }) };
  return { cents };
}

export const centsToMarks = cents => (cents / 100).toFixed(2);
export const marksToCents = marks => Math.round(Number(marks) * 100);

/** FR03: title, positive duration and total, close after open. */
export function detailsIssues(d) {
  const found = [];
  if (!String(d.title ?? "").trim()) found.push(issue("required", "Enter a title.", { field: "title" }));
  const opens = Date.parse(d.opens_at), closes = Date.parse(d.closes_at);
  if (Number.isNaN(opens)) found.push(issue("required", "Choose when the exam opens.", { field: "opens_at" }));
  if (Number.isNaN(closes)) found.push(issue("required", "Choose when the exam closes.", { field: "closes_at" }));
  if (!(Number.isInteger(Number(d.duration_minutes)) && Number(d.duration_minutes) > 0)) {
    found.push(issue("non_positive_duration", "Duration must be a whole number of minutes above zero.", { field: "duration_minutes" }));
  }
  const total = parseMarks(d.total_marks, "total_marks");
  if (total.issue) found.push(total.issue);
  if (!Number.isNaN(opens) && !Number.isNaN(closes) && closes <= opens) {
    found.push(issue("close_before_open", "The exam must close after it opens.", { field: "closes_at" }));
  }
  return found;
}

/** FR04/FR05: options, keys and marking rule for one question version. */
export function questionIssues(q) {
  const found = [];
  const options = q.options ?? [];
  const keys = q.correct_option_ids ?? [];
  if (!String(q.topic ?? "").trim()) found.push(issue("required", "Enter a topic.", { field: "topic" }));
  if (!String(q.prompt ?? "").trim()) found.push(issue("required", "Enter the question prompt.", { field: "prompt" }));
  if (!RULES_FOR_KIND[q.kind]?.includes(q.marking_rule)) {
    found.push(issue("rule_mismatch", `A ${q.kind} question uses ${(RULES_FOR_KIND[q.kind] ?? []).join(" or ")} marking.`, { field: "marking_rule" }));
  }
  if (q.kind === "written") {
    if (options.length) found.push(issue("written_has_options", "Written questions take no options.", { field: "options" }));
    return found;
  }
  if (options.length < 2) found.push(issue("too_few_options", "Objective questions need at least two options.", { field: "options" }));
  if (options.some(o => !String(o.label ?? "").trim())) found.push(issue("empty_option", "Every option needs a label.", { field: "options" }));
  const labels = options.map(o => String(o.label ?? "").trim().toLowerCase()).filter(Boolean);
  if (new Set(labels).size !== labels.length) found.push(issue("duplicate_option_label", "Option labels must differ.", { field: "options" }));
  const ids = new Set(options.map(o => o.id));
  if (keys.some(k => !ids.has(k))) found.push(issue("unknown_key", "A key matches no option.", { field: "correct_option_ids" }));
  if (q.kind === "single" && keys.length !== 1) {
    found.push(issue("single_key_count", `Single-answer questions need exactly one key; ${keys.length} marked.`, { field: "correct_option_ids" }));
  }
  if (q.kind === "multiple" && keys.length < 1) {
    found.push(issue("multiple_key_count", "Multiple-select questions need at least one key.", { field: "correct_option_ids" }));
  }
  return found;
}

/**
 * The mark ledger: how the slots fill the declared total.
 * Returns cents so the arithmetic is exact.
 */
export function tally(items, totalMarks) {
  const declared = parseMarks(totalMarks, "total_marks").cents ?? 0;
  const segments = items.map(i => ({ slot: i.slot, cents: parseMarks(i.max_marks).cents ?? 0 }));
  const allocated = segments.reduce((sum, s) => sum + s.cents, 0);
  return {
    declared, allocated, segments,
    remaining: Math.max(declared - allocated, 0),
    excess: Math.max(allocated - declared, 0),
    balanced: declared > 0 && allocated === declared && items.length > 0,
  };
}

/** Group issues by a key ("field", "item" or "row") for inline placement. */
export function groupIssues(issues = [], key = "field") {
  const grouped = new Map();
  for (const i of issues) {
    const k = i[key] ?? null;
    if (!grouped.has(k)) grouped.set(k, []);
    grouped.get(k).push(i);
  }
  return grouped;
}

/**
 * FR05 publication checklist, mirroring PublicationPolicy on the server.
 * `exam.items[*].version` holds the pinned version body.
 */
export function reviewPublication(exam, now = new Date()) {
  const check = (name, label, issues) => ({ name, label, passed: issues.length === 0, issues });
  const items = exam.items ?? [];
  const particulars = detailsIssues(exam).filter(i => i.field !== "total_marks");
  const window = Date.parse(exam.closes_at) <= now.getTime()
    ? [issue("window_passed", "The closing time has already passed.", { field: "closes_at" })] : [];
  const nonempty = items.length ? [] : [issue("empty_paper", "Add at least one question to the paper.", { field: "items" })];
  const seen = new Set(), distinct = [];
  for (const i of items) {
    if (seen.has(i.question_id)) distinct.push(issue("duplicate_question", "A bank question may appear only once.", { field: "question_id", item: i.slot }));
    seen.add(i.question_id);
  }
  const keys = items.flatMap(i => questionIssues(i.version).map(x => ({ ...x, item: i.slot })));
  const t = tally(items, exam.total_marks);
  const total = [];
  for (const i of items) {
    const parsed = parseMarks(i.max_marks);
    if (parsed.issue) total.push({ ...parsed.issue, item: i.slot });
  }
  if (items.length && t.allocated !== t.declared) {
    total.push(issue("total_mismatch", `Item marks add up to ${centsToMarks(t.allocated)} but the declared total is ${centsToMarks(t.declared)}.`, { field: "total_marks" }));
  }
  const checks = [
    check("particulars", "Title, window and duration are valid", particulars),
    check("window", "The exam has not closed yet", window),
    check("nonempty", "The paper has at least one question", nonempty),
    check("ownership", "Every question comes from your bank", []),
    check("distinct", "Each bank question appears once", distinct),
    check("keys", "Options and answer keys are valid", keys),
    check("total", "Item marks add up to the declared total", total),
  ];
  return { ready: checks.every(c => c.passed), checks };
}

/** Derived exam state from publication and the window (server time in production). */
export function examState(exam, now = new Date()) {
  if (!exam.published_at) return "draft";
  const t = now.getTime();
  if (t < Date.parse(exam.opens_at)) return "scheduled";
  if (t < Date.parse(exam.closes_at)) return "ongoing";
  return "completed";
}

/**
 * One-click ways to make the paper add up (user analysis: the most common
 * publish blocker). Each option is a plain descriptor; the page applies it.
 *   { kind: "set_total", cents }                       declare what is allocated
 *   { kind: "adjust_slot", slot, fromCents, toCents }  move the gap onto one slot
 */
export function balanceOptions(slots, totalMarks) {
  const t = tally(slots, totalMarks);
  if (!slots.length || t.balanced) return [];
  const options = [];
  if (t.allocated > 0) options.push({ kind: "set_total", cents: t.allocated });
  if (t.remaining > 0 && t.declared > 0) {
    const last = t.segments[t.segments.length - 1];
    options.push({ kind: "adjust_slot", slot: last.slot, fromCents: last.cents, toCents: last.cents + t.remaining });
  }
  if (t.excess > 0) {
    const largest = [...t.segments].sort((a, b) => b.cents - a.cents || b.slot - a.slot)[0];
    if (largest.cents - t.excess > 0) {
      options.push({ kind: "adjust_slot", slot: largest.slot, fromCents: largest.cents, toCents: largest.cents - t.excess });
    }
  }
  return options;
}
