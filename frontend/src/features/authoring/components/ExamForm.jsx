import React, { useState } from "react";
import { detailsIssues, groupIssues } from "../domain/rules.js";
import { formatDuration, fromLocalInput, toLocalInput } from "../domain/format.js";
import { ErrorSummary, Field } from "./primitives.jsx";

export const blankDetails = () => {
  const start = new Date(Date.now() + 7 * 864e5);
  start.setHours(10, 30, 0, 0);
  return { title: "", instructions: "", opens_at: start.toISOString(), closes_at: new Date(start.getTime() + 30 * 6e4).toISOString(),
    duration_minutes: 30, total_marks: "10.00", shuffle_questions: false, shuffle_choices: false };
};

/** FR03 particulars: title, instructions, window, duration, total, shuffle. */
export function ExamForm({ initial, submitLabel, onSubmit, onCancel, onDirty }) {
  const [values, setValues] = useState(() => ({ ...initial, opens_local: toLocalInput(initial.opens_at), closes_local: toLocalInput(initial.closes_at) }));
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(false);
  const set = (field, value) => { setValues(v => ({ ...v, [field]: value })); onDirty?.(true); };
  const body = () => ({
    title: values.title, instructions: values.instructions,
    opens_at: fromLocalInput(values.opens_local), closes_at: fromLocalInput(values.closes_local),
    duration_minutes: Number(values.duration_minutes), total_marks: String(values.total_marks).trim(),
    shuffle_questions: values.shuffle_questions, shuffle_choices: values.shuffle_choices,
  });

  async function submit(e) {
    e.preventDefault();
    const issues = detailsIssues(body());
    if (issues.length) { setError({ issues }); return; }
    setPending(true); setError(null);
    try { await onSubmit(body()); onDirty?.(false); }
    catch (err) { setError(err.issues?.length ? err : { message: err.message, issues: [] }); }
    finally { setPending(false); }
  }

  const byField = groupIssues(error?.issues);
  const of = name => byField.get(name) ?? [];
  const windowMinutes = (Date.parse(fromLocalInput(values.closes_local)) - Date.parse(fromLocalInput(values.opens_local))) / 6e4;
  return <form className="au-form" onSubmit={submit} noValidate>
    <ErrorSummary error={error} />
    <Field label="Title" issues={of("title")}><input value={values.title} onChange={e => set("title", e.target.value)} maxLength={300} autoComplete="off" /></Field>
    <Field label="Instructions" hint="Shown to enrolled candidates before the exam opens." issues={of("instructions")}>
      <textarea rows={3} value={values.instructions} onChange={e => set("instructions", e.target.value)} />
    </Field>
    <div className="au-form__grid">
      <Field label="Opens" issues={of("opens_at")}><input type="datetime-local" value={values.opens_local} onChange={e => set("opens_local", e.target.value)} /></Field>
      <Field label="Closes" issues={of("closes_at")} hint={windowMinutes > 0 ? `Window: ${formatDuration(windowMinutes)}` : undefined}>
        <input type="datetime-local" value={values.closes_local} onChange={e => set("closes_local", e.target.value)} /></Field>
      <Field label="Duration (minutes)" issues={of("duration_minutes")}
        hint={windowMinutes > 0 && Number(values.duration_minutes) > windowMinutes ? "Longer than the window: late starters are capped at closing." : "Per attempt. Capped at the closing time."}>
        <input type="number" inputMode="numeric" min="1" step="1" value={values.duration_minutes} onChange={e => set("duration_minutes", e.target.value)} /></Field>
      <Field label="Declared total marks" issues={of("total_marks")} hint="Slot marks must add up to this.">
        <input inputMode="decimal" value={values.total_marks} onChange={e => set("total_marks", e.target.value)} /></Field>
    </div>
    <fieldset className="au-form__toggles"><legend className="au-field__label">Shuffle for each candidate</legend>
      <label className="au-check"><input type="checkbox" checked={values.shuffle_questions} onChange={e => set("shuffle_questions", e.target.checked)} /> Question order</label>
      <label className="au-check"><input type="checkbox" checked={values.shuffle_choices} onChange={e => set("shuffle_choices", e.target.checked)} /> Choice order</label>
    </fieldset>
    <p className="au-form__zone">Times use this device’s time zone and are stored with their offset.</p>
    <div className="actions">
      <span />
      <div className="row">{onCancel && <button type="button" className="secondary" onClick={onCancel}>Cancel</button>}
        <button className="primary" disabled={pending}>{pending ? "Saving…" : submitLabel}</button></div>
    </div>
  </form>;
}
