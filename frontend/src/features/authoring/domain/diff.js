// What changed between two question versions. Word-level diff for text;
// options are matched by their stable IDs so relabels and key moves are exact.

const MAX_TOKENS = 800;

/** Longest-common-subsequence diff over words and whitespace. */
export function wordDiff(before = "", after = "") {
  const tokens = text => text.split(/(\s+|[.,;:!?()"“”])/).filter(Boolean);
  const a = tokens(before), b = tokens(after);
  if (a.length > MAX_TOKENS || b.length > MAX_TOKENS) {
    return before === after ? [{ op: "same", text: after }] : [{ op: "del", text: before }, { op: "ins", text: after }];
  }
  const lcs = Array.from({ length: a.length + 1 }, () => new Uint16Array(b.length + 1));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const out = [];
  const push = (op, text) => { const last = out[out.length - 1]; if (last?.op === op) last.text += text; else out.push({ op, text }); };
  let i = 0, j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { push("same", a[i]); i++; j++; }
    else if (lcs[i + 1][j] >= lcs[i][j + 1]) push("del", a[i++]);
    else push("ins", b[j++]);
  }
  while (i < a.length) push("del", a[i++]);
  while (j < b.length) push("ins", b[j++]);
  return out;
}

const FIELDS = [["topic", "Topic"], ["difficulty", "Difficulty"], ["kind", "Type"], ["marking_rule", "Marking rule"], ["rubric", "Rubric"]];

/** Structured changes from `prev` to `next`. */
export function versionChanges(prev, next) {
  const fields = FIELDS.filter(([k]) => (prev[k] ?? "") !== (next[k] ?? ""))
    .map(([key, label]) => ({ key, label, from: prev[key] ?? "", to: next[key] ?? "" }));
  const before = new Map(prev.options.map(o => [o.id, o])), after = new Map(next.options.map(o => [o.id, o]));
  const options = [];
  for (const o of next.options) {
    const old = before.get(o.id);
    if (!old) options.push({ id: o.id, change: "added", label: o.label, correct: o.correct });
    else {
      const relabeled = old.label !== o.label, key = old.correct !== o.correct;
      if (relabeled || key) options.push({ id: o.id, change: "changed", from: old.label, label: o.label, relabeled, keyNow: key ? o.correct : undefined });
    }
  }
  for (const o of prev.options) if (!after.has(o.id)) options.push({ id: o.id, change: "removed", label: o.label, correct: o.correct });
  const prompt = prev.prompt === next.prompt ? null : wordDiff(prev.prompt, next.prompt);
  return { prompt, fields, options, empty: !prompt && !fields.length && !options.length };
}
