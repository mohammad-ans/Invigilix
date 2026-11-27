import React, { useState } from "react";
import { DIFFICULTIES, KINDS, RULES_FOR_KIND, groupIssues, questionIssues } from "../domain/rules.js";
import { KIND, RULE, letter } from "../domain/format.js";
import { ErrorSummary, Field } from "./primitives.jsx";

export const blankQuestion = () => ({
  topic: "", difficulty: "medium", kind: "single", prompt: "", marking_rule: "exact", rubric: "",
  options: [{ id: 1, label: "" }, { id: 2, label: "" }], correct_option_ids: [],
});

/** Create or revise a question version (FR04). Keys stay examiner-side. */
export function QuestionForm({ initial, submitLabel, onSubmit, onCancel, note }) {
  const [q, setQ] = useState(() => ({ ...blankQuestion(), ...initial, rubric: initial?.rubric ?? "",
    options: (initial?.options ?? blankQuestion().options).map(o => ({ id: o.id, label: o.label })) }));
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(false);
  const set = patch => setQ(prev => ({ ...prev, ...patch }));
  const objective = q.kind !== "written";

  function changeKind(kind) {
    const options = kind === "written" ? [] : q.options.length >= 2 ? q.options : blankQuestion().options;
    const keys = kind === "single" ? q.correct_option_ids.slice(0, 1) : kind === "written" ? [] : q.correct_option_ids;
    set({ kind, options, correct_option_ids: keys, marking_rule: RULES_FOR_KIND[kind].includes(q.marking_rule) ? q.marking_rule : RULES_FOR_KIND[kind][0] });
  }
  function toggleKey(id) {
    if (q.kind === "single") set({ correct_option_ids: [id] });
    else set({ correct_option_ids: q.correct_option_ids.includes(id) ? q.correct_option_ids.filter(k => k !== id) : [...q.correct_option_ids, id].sort((a, b) => a - b) });
  }
  const addOption = () => set({ options: [...q.options, { id: Math.max(0, ...q.options.map(o => o.id)) + 1, label: "" }] });
  const removeOption = id => set({ options: q.options.filter(o => o.id !== id), correct_option_ids: q.correct_option_ids.filter(k => k !== id) });

  const body = () => ({ topic: q.topic.trim(), difficulty: q.difficulty, kind: q.kind, prompt: q.prompt.trim(), marking_rule: q.marking_rule,
    options: objective ? q.options.map(o => ({ id: o.id, label: o.label.trim() })) : [],
    correct_option_ids: objective ? q.correct_option_ids : [], rubric: q.rubric.trim() || null });

  async function submit(e) {
    e.preventDefault();
    const issues = questionIssues(body());
    if (issues.length) { setError({ issues }); return; }
    setPending(true); setError(null);
    try { await onSubmit(body()); }
    catch (err) { setError(err.issues?.length ? err : { message: err.message, issues: [] }); }
    finally { setPending(false); }
  }

  const of = name => groupIssues(error?.issues).get(name) ?? [];
  const keyIssues = of("correct_option_ids");
  return <form className="au-form au-qform" onSubmit={submit} noValidate>
    <ErrorSummary error={error} />
    <fieldset className="au-segmented"><legend className="au-field__label">Question type</legend>
      {KINDS.map(k => <label key={k} className={q.kind === k ? "on" : ""}><input type="radio" name="kind" value={k} checked={q.kind === k} onChange={() => changeKind(k)} />{KIND[k].label}</label>)}
    </fieldset>
    <Field label="Prompt" issues={of("prompt")}><textarea rows={3} className="au-prompt-input" value={q.prompt} onChange={e => set({ prompt: e.target.value })} /></Field>
    <div className="au-form__grid">
      <Field label="Topic" issues={of("topic")}><input value={q.topic} onChange={e => set({ topic: e.target.value })} maxLength={300} /></Field>
      <Field label="Difficulty" issues={of("difficulty")}><select value={q.difficulty} onChange={e => set({ difficulty: e.target.value })}>
        {DIFFICULTIES.map(d => <option key={d} value={d}>{d[0].toUpperCase() + d.slice(1)}</option>)}</select></Field>
      <Field label="Marking rule" issues={of("marking_rule")} hint={q.kind === "multiple" && q.marking_rule === "partial_no_wrong" ? "Cap × correct chosen ÷ total correct; any wrong choice scores zero." : undefined}>
        <select value={q.marking_rule} onChange={e => set({ marking_rule: e.target.value })} disabled={RULES_FOR_KIND[q.kind].length === 1}>
          {RULES_FOR_KIND[q.kind].map(r => <option key={r} value={r}>{RULE[r]}</option>)}</select></Field>
    </div>

    {objective && <fieldset className={`au-options${keyIssues.length || of("options").length ? " au-options--invalid" : ""}`}>
      <legend className="au-field__label">Options and key <span className="au-sub au-inline">· {q.kind === "single" ? "mark exactly one correct option" : "mark every correct option"}</span></legend>
      <ol>{q.options.map((o, n) => {
        const isKey = q.correct_option_ids.includes(o.id);
        return <li key={o.id} className={isKey ? "au-option--key" : ""}>
          <span className="opt-letter" aria-hidden="true">{letter(n)}</span>
          <input aria-label={`Option ${letter(n)} label`} aria-invalid={error && !o.label.trim() ? true : undefined} value={o.label} onChange={e => set({ options: q.options.map(x => x.id === o.id ? { ...x, label: e.target.value } : x) })} />
          <label className="au-key"><input type={q.kind === "single" ? "radio" : "checkbox"} name="key" checked={isKey} onChange={() => toggleKey(o.id)} />
            <span>{isKey ? "✓ Key" : "Key"}</span><span className="sr-only"> for option {letter(n)}</span></label>
          <button type="button" className="au-icon au-icon--remove" disabled={q.options.length <= 2} onClick={() => removeOption(o.id)} aria-label={`Remove option ${letter(n)}`}>×</button>
        </li>;
      })}</ol>
      {[...of("options"), ...keyIssues].map((i, n) => <p key={n} className="au-field__error"><b aria-hidden="true">✕</b> {i.message}</p>)}
      <button type="button" className="quiet" disabled={q.options.length >= 26} onClick={addOption}>＋ Add option</button>
    </fieldset>}

    {!objective && <Field label="Marking rubric (private)" hint="Visible to examiners only. Never sent to candidates." issues={of("rubric")}>
      <textarea rows={3} value={q.rubric} onChange={e => set({ rubric: e.target.value })} /></Field>}

    {note && <p className="au-form__zone">{note}</p>}
    <div className="actions"><span />
      <div className="row">{onCancel && <button type="button" className="secondary" onClick={onCancel}>Cancel</button>}
        <button className="primary" disabled={pending}>{pending ? "Saving…" : submitLabel}</button></div></div>
  </form>;
}
