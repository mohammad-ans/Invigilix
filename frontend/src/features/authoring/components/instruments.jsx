import React, { useRef } from "react";
import { centsToMarks, tally } from "../domain/rules.js";
import { formatDate, two } from "../domain/format.js";
import { useFocusTrap } from "../hooks.js";

/**
 * The mark ledger: one ruled bar where each slot occupies its share of the
 * declared total. Unallocated marks show as an open dashed segment; marks
 * beyond the total overflow in hatched rust. The sentence below states the
 * same facts in words for screen readers and colour-blind readers.
 */
export function MarkLedger({ items, totalMarks, compact = false }) {
  const t = tally(items, totalMarks);
  const scale = Math.max(t.declared, t.allocated, 1);
  const pct = cents => `${(100 * cents) / scale}%`;
  const verdict = t.balanced ? "balanced" : t.excess ? "over" : "under";
  return <figure className={`au-ledger au-ledger--${verdict}${compact ? " au-ledger--compact" : ""}`}>
    <div className="au-ledger__figures">
      <span><span className="mini">Allocated</span><strong>{centsToMarks(t.allocated)}</strong></span>
      <span className="au-ledger__of" aria-hidden="true">of</span>
      <span><span className="mini">Declared total</span><strong>{centsToMarks(t.declared)}</strong></span>
    </div>
    <div className="au-ledger__bar" aria-hidden="true">
      {t.segments.map(s => <span key={s.slot} className="au-ledger__seg" style={{ width: pct(Math.min(s.cents, scale)) }}><em>{two(s.slot)}</em></span>)}
      {t.remaining > 0 && <span className="au-ledger__gap" style={{ width: pct(t.remaining) }} />}
      {t.excess > 0 && <span className="au-ledger__limit" style={{ left: pct(t.declared) }} />}
    </div>
    <figcaption className="au-ledger__caption" aria-live="polite">
      {t.balanced && <><b aria-hidden="true">✓</b> Item marks match the declared total.</>}
      {verdict === "under" && <><b aria-hidden="true">!</b> {items.length ? `${centsToMarks(t.remaining)} marks unallocated.` : "No questions on the paper yet."}</>}
      {verdict === "over" && <><b aria-hidden="true">✕</b> {centsToMarks(t.excess)} marks over the declared total.</>}
    </figcaption>
  </figure>;
}

/** Publication checklist rendered like a proof-reader's margin. */
export function Checklist({ publication, onJump }) {
  if (!publication) return null;
  const failing = publication.checks.filter(c => !c.passed).length;
  return <section className="au-checklist" aria-labelledby="checklist-title">
    <div className="split"><h3 id="checklist-title" className="au-subhead">Publication check</h3>
      <span className={`au-tally ${failing ? "au-tally--open" : "au-tally--done"}`}>{failing ? `${failing} to resolve` : "Ready"}</span></div>
    <ol className="au-checklist__list">
      {publication.checks.map(c => <li key={c.name} className={c.passed ? "pass" : "fail"}>
        <span className="au-checklist__mark" aria-hidden="true">{c.passed ? "✓" : "✕"}</span>
        <div><span className="sr-only">{c.passed ? "Passed: " : "Needs attention: "}</span>{c.label}
          {c.issues.length > 0 && <ul>{c.issues.map((i, n) => <li key={n}>
            {i.item ? <button type="button" className="au-link" onClick={() => onJump?.(i.item)}>Slot {two(i.item)}</button> : null}
            {i.item ? " · " : ""}{i.message}</li>)}</ul>}
        </div>
      </li>)}
    </ol>
  </section>;
}

/** The stamped record of a frozen paper. */
export function FrozenSeal({ publishedAt, itemCount }) {
  return <div className="au-seal" role="note" aria-label="Published and frozen">
    <div className="au-seal__stamp" aria-hidden="true"><span>Folio</span><b>Frozen</b><span>{new Date(publishedAt).getFullYear()}</span></div>
    <div className="au-seal__text">
      <strong>Published paper · frozen record</strong>
      <p>Published {formatDate(publishedAt, { withZone: true })}. The {itemCount} slots, their question versions, marks, schedule and settings can no longer change. Bank edits create new versions and leave this paper untouched.</p>
    </div>
  </div>;
}

/** Modal dialog with focus trap, Escape to close and focus restoration. */
export function Dialog({ title, onClose, children, wide = false, labelledBy }) {
  const ref = useRef(null);
  useFocusTrap(ref, onClose);
  return <div className="dialog-scrim" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
    <section ref={ref} className={`dialog au-dialog${wide ? " au-dialog--wide" : ""}`} role="dialog" aria-modal="true" aria-labelledby={labelledBy ?? "au-dialog-title"}>
      <div className="split au-dialog__head"><h2 id="au-dialog-title">{title}</h2>
        <button type="button" className="au-close" onClick={onClose} aria-label="Close dialog">×</button></div>
      {children}
    </section>
  </div>;
}
