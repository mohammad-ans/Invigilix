import React, { useEffect, useId, useRef } from "react";
import { ACCESS, KIND, STATE } from "../domain/format.js";

/** Exam state with a glyph, a word and a tone. Never colour alone. */
export function StateBadge({ state, size }) {
  const s = STATE[state] ?? STATE.draft;
  return <span className={`au-state au-state--${s.tone}${size ? " au-state--" + size : ""}`} title={s.hint}>
    <span aria-hidden="true" className="au-state__glyph">{s.glyph}</span>{s.label}
  </span>;
}

export function AccessBadge({ access }) {
  const a = ACCESS[access] ?? { label: access, tone: "muted" };
  const glyph = { ok: "✓", pending: "◷", muted: "–", error: "✕" }[a.tone];
  return <span className={`au-access au-access--${a.tone}`}><span aria-hidden="true">{glyph}</span>{a.label}</span>;
}

export function KindTag({ kind }) {
  const glyph = { single: "◉", multiple: "☑", written: "¶" }[kind];
  return <span className="au-kind"><span aria-hidden="true">{glyph}</span>{KIND[kind]?.short ?? kind}</span>;
}

/** Three ruled bars, filled by difficulty, with the word beside them. */
export function DifficultyScale({ level }) {
  const n = { easy: 1, medium: 2, hard: 3 }[level] ?? 0;
  return <span className="au-difficulty">
    <span className="au-difficulty__bars" aria-hidden="true">{[1, 2, 3].map(i => <i key={i} className={i <= n ? "on" : ""} />)}</span>
    <span className="au-difficulty__label">{level}</span>
  </span>;
}

export function VersionTag({ number, latest }) {
  return <span className="au-version" title={latest && latest > number ? `Version ${latest} exists in the bank` : undefined}>v{number}</span>;
}

/** A labelled control with hint and inline error, wired with aria-describedby. */
export function Field({ label, hint, issues = [], children, className = "", as = "label" }) {
  const id = useId();
  const hintId = hint ? id + "-hint" : undefined, errorId = issues.length ? id + "-error" : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  const control = React.Children.map(children, child => React.isValidElement(child)
    ? React.cloneElement(child, { id: child.props.id ?? id, "aria-describedby": describedBy, "aria-invalid": issues.length ? true : undefined })
    : child);
  const Tag = as;
  return <div className={`au-field ${issues.length ? "au-field--invalid" : ""} ${className}`}>
    {Tag === "label" ? <label htmlFor={id} className="au-field__label">{label}</label> : <span className="au-field__label" id={id + "-label"}>{label}</span>}
    {hint && <span className="au-field__hint" id={hintId}>{hint}</span>}
    {control}
    {issues.length > 0 && <span className="au-field__error" id={errorId}>{issues.map(i => <span key={i.code + i.message}><b aria-hidden="true">✕</b> {i.message}</span>)}</span>}
  </div>;
}

/** Error summary at the top of a form. Receives focus when it appears. */
export function ErrorSummary({ error, title = "Check the highlighted fields", describe }) {
  const ref = useRef(null);
  useEffect(() => { if (error) ref.current?.focus(); }, [error]);
  if (!error) return null;
  const issues = error.issues ?? [];
  return <div className="au-banner au-banner--error" role="alert" tabIndex={-1} ref={ref}>
    <span className="au-banner__mark" aria-hidden="true">!</span>
    <div><strong>{issues.length ? title : error.message}</strong>
      {issues.length > 0 && <ul className="au-issues">{issues.map((i, n) => <li key={n}>{describe ? describe(i) : i.message}</li>)}</ul>}
    </div>
  </div>;
}

export function Banner({ tone = "info", title, children, mark }) {
  const glyph = mark ?? { info: "i", warn: "!", error: "!", ok: "✓", frozen: "⌂" }[tone];
  return <div className={`au-banner au-banner--${tone}`} role={tone === "error" ? "alert" : "status"}>
    <span className="au-banner__mark" aria-hidden="true">{glyph}</span>
    <div>{title && <strong>{title}</strong>}{children && <div className="au-banner__body">{children}</div>}</div>
  </div>;
}

/** Ruled-paper empty state: what is missing and the one action that fixes it. */
export function EmptyState({ title, children, action, art }) {
  return <div className="au-empty">
    {art ?? <div className="au-empty__page" aria-hidden="true"><i /><i /><i /><i /></div>}
    <h3>{title}</h3>
    {children && <p>{children}</p>}
    {action}
  </div>;
}

export function Loading({ label = "Loading" }) {
  return <div className="au-loading" role="status"><span className="au-loading__rule" aria-hidden="true" />{label}…</div>;
}

export function LoadError({ error, retry }) {
  const notFound = error?.status === 404;
  return <Banner tone="error" title={notFound ? "This record is not available" : "This page could not load"}>
    <p>{notFound ? "It may not exist, or it belongs to another examiner." : error?.message}</p>
    {!notFound && retry && <button className="secondary" onClick={retry}>Try again</button>}
  </Banner>;
}

export function Stat({ label, value, tone }) {
  return <div className={`stat${tone ? " au-stat--" + tone : ""}`}><span className="mini">{label}</span><strong>{value}</strong></div>;
}

/** Labels the data source so preview records are never mistaken for real ones. */
export function ModeLabel({ mode }) {
  if (mode !== "preview") return null;
  return <span className="au-mode" title="Fictional records held in this browser tab">Preview data</span>;
}
