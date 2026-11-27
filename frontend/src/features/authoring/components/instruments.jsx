import React, { useId, useRef } from "react";
import { balanceOptions, centsToMarks, tally } from "../domain/rules.js";
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

/**
 * One-click remedies for a paper that does not add up, placed in the message
 * that reports the problem. Declaring the allocated total saves at once; moving
 * the gap onto a slot is a draft edit the examiner still saves.
 */
export function BalanceFixes({ slots, totalMarks, totalBlockedReason, onSetTotal, onAdjustSlot }) {
  const options = balanceOptions(slots, totalMarks);
  if (!options.length) return null;
  return <div className="au-fixes" role="group" aria-label="Make the marks add up">
    {options.map(o => o.kind === "set_total"
      ? <button key="total" type="button" className="au-fix" disabled={Boolean(totalBlockedReason)} onClick={() => onSetTotal(o.cents)}>
          Set declared total to <b>{centsToMarks(o.cents)}</b></button>
      : <button key={`slot-${o.slot}`} type="button" className="au-fix" onClick={() => onAdjustSlot(o.slot, o.toCents)}>
          Slot {two(o.slot)}: {centsToMarks(o.fromCents)} <span aria-hidden="true">→</span><span className="sr-only">to</span> <b>{centsToMarks(o.toCents)}</b></button>)}
    {totalBlockedReason && <p className="au-sub">{totalBlockedReason}</p>}
  </div>;
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

/** A rubber stamp: legend set around the ring, the mark and date in the
 *  centre, edges roughened by a displacement filter so it reads as ink. */
export function Stamp({ date, mark = "Frozen", legend = "Folio · Examination office · Frozen paper ·", className = "" }) {
  const id = useId().replace(/:/g, "");
  const day = new Date(date).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }).toUpperCase();
  return <svg className={`au-stamp ${className}`} viewBox="0 0 120 120" aria-hidden="true">
    <defs>
      <path id={`${id}-ring`} d="M60 60m-43.5 0a43.5 43.5 0 1 1 87 0a43.5 43.5 0 1 1-87 0" />
      <filter id={`${id}-ink`} x="-5%" y="-5%" width="110%" height="110%">
        <feTurbulence type="fractalNoise" baseFrequency="1.1" numOctaves="2" seed="7" result="n" />
        <feDisplacementMap in="SourceGraphic" in2="n" scale="1.8" />
      </filter>
    </defs>
    <g filter={`url(#${id}-ink)`} fill="none" stroke="currentColor">
      <circle cx="60" cy="60" r="56" strokeWidth="2.2" />
      <circle cx="60" cy="60" r="51.5" strokeWidth=".8" />
      <circle cx="60" cy="60" r="35" strokeWidth=".8" />
      <text fill="currentColor" stroke="none" fontFamily="var(--mono)" fontSize="8" fontWeight="600" letterSpacing="1.4">
        <textPath href={`#${id}-ring`} textLength="268" lengthAdjust="spacingAndGlyphs">{legend.toUpperCase()}</textPath>
      </text>
      <text x="60" y="61" textAnchor="middle" fill="currentColor" stroke="none" fontFamily="var(--serif)" fontStyle="italic" fontWeight="600" fontSize="17">{mark}</text>
      <path d="M40 67h40" strokeWidth=".7" />
      <text x="60" y="76" textAnchor="middle" fill="currentColor" stroke="none" fontFamily="var(--mono)" fontSize="6.4" letterSpacing=".6">{day}</text>
    </g>
  </svg>;
}

/** The stamped record of a frozen paper. */
export function FrozenSeal({ publishedAt, itemCount, fresh = false }) {
  return <div className={`au-seal${fresh ? " au-seal--fresh" : ""}`} role="note" aria-label="Published and frozen">
    <div className="au-seal__stamp"><Stamp date={publishedAt} /></div>
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
