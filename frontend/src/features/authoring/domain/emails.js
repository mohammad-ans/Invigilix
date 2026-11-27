// Live reading of pasted candidate emails (user analysis: a single typo used
// to reject the whole batch only after submitting). Same address pattern as
// the server's candidate import.
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Split pasted text into tokens: { text, status: "ok" | "malformed" | "repeat" }. */
export function parseEmailList(text) {
  const seen = new Set();
  return String(text ?? "").split(/[\s,;]+/).map(t => t.trim()).filter(Boolean).map(t => {
    const key = t.toLowerCase();
    if (!EMAIL.test(t)) return { text: t, status: "malformed" };
    if (seen.has(key)) return { text: t, status: "repeat" };
    seen.add(key);
    return { text: t, status: "ok" };
  });
}

export const usable = tokens => tokens.filter(t => t.status === "ok").map(t => t.text);
