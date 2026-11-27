// Presentation helpers. Times arrive as ISO 8601 instants with an offset and
// are shown in the viewer's zone with the zone named, so nothing is ambiguous.

export const two = n => String(n).padStart(2, "0");

export const STATE = {
  draft: { label: "Draft", glyph: "✎", tone: "draft", hint: "Editable. Candidates cannot see it." },
  scheduled: { label: "Scheduled", glyph: "◷", tone: "scheduled", hint: "Published. Opens later; questions withheld." },
  ongoing: { label: "Ongoing", glyph: "●", tone: "ongoing", hint: "Window open. Eligible candidates can start." },
  completed: { label: "Completed", glyph: "■", tone: "completed", hint: "Window closed. Entry is closed." },
};

export const ACCESS = {
  available: { label: "Can enter now", tone: "ok" },
  upcoming: { label: "Can enter at opening", tone: "ok" },
  completed: { label: "Window closed", tone: "muted" },
  awaiting_publication: { label: "Awaiting publication", tone: "pending" },
  enrollment_inactive: { label: "Withdrawn", tone: "muted" },
  account_disabled: { label: "Account disabled", tone: "error" },
  not_candidate: { label: "Not a candidate", tone: "error" },
  not_enrolled: { label: "Not enrolled", tone: "muted" },
};

export const KIND = {
  single: { label: "Single answer", short: "Single" },
  multiple: { label: "Multiple select", short: "Multiple" },
  written: { label: "Written", short: "Written" },
};

export const RULE = {
  exact: "Exact match",
  partial_no_wrong: "Partial credit, no wrong choice",
  manual: "Examiner marks",
};

const zone = () => {
  try { return new Intl.DateTimeFormat(undefined, { timeZoneName: "short" }).formatToParts(new Date()).find(p => p.type === "timeZoneName")?.value ?? ""; }
  catch { return ""; }
};

export function formatDate(iso, { withZone = false } = {}) {
  if (!iso) return "—";
  const d = new Date(iso);
  const date = d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
  const time = d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  return `${date} · ${time}${withZone ? " " + zone() : ""}`;
}

export function formatWindow(opens, closes) {
  if (!opens || !closes) return "—";
  const a = new Date(opens), b = new Date(closes);
  const day = a.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
  const t = d => d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  const sameDay = a.toDateString() === b.toDateString();
  return sameDay ? `${day} · ${t(a)}–${t(b)}` : `${day} ${t(a)} → ${b.toLocaleDateString(undefined, { day: "2-digit", month: "short" })} ${t(b)}`;
}

export function formatDuration(minutes) {
  const m = Number(minutes);
  if (!Number.isFinite(m)) return "—";
  const h = Math.floor(m / 60), r = m % 60;
  return h ? `${h} h${r ? ` ${r} min` : ""}` : `${r} min`;
}

export const formatMarks = value => (value === undefined || value === null || value === "" ? "—" : Number(value).toFixed(2));

/** <input type="datetime-local"> value ⇄ ISO instant with explicit offset. */
export function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}T${two(d.getHours())}:${two(d.getMinutes())}`;
}
export function fromLocalInput(value) {
  if (!value) return "";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "" : d.toISOString();
}

export const letter = index => String.fromCharCode(65 + index);
export const shortId = id => String(id ?? "").slice(0, 8).toUpperCase();
