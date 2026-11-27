import React, { useId } from "react";
import { ATTEMPT_STATUS_META } from "../domain/rules.js";
import { axisTicks, digestGroups, pips, stackScores } from "../domain/visuals.js";

const two = n => String(n).padStart(2, "0");

/**
 * Rubber stamp in ink: legend around the ring, mark and date in the centre,
 * edges roughened so it reads as a real impression. (Same drawing as the
 * authoring frozen seal; a candidate for design/ in a foundation PR.)
 */
export function Stamp({ mark, legend, date, tone = "forest", className = "" }) {
  const id = useId().replace(/:/g, "");
  const day = date ? new Date(date).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }).toUpperCase() : "";
  return <svg className={`res-stamp res-stamp--${tone} ${className}`} viewBox="0 0 120 120" aria-hidden="true">
    <defs>
      <path id={`${id}-ring`} d="M60 60m-43.5 0a43.5 43.5 0 1 1 87 0a43.5 43.5 0 1 1-87 0" />
      <filter id={`${id}-ink`} x="-5%" y="-5%" width="110%" height="110%">
        <feTurbulence type="fractalNoise" baseFrequency="1.1" numOctaves="2" seed="11" result="n" />
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
      <text x="60" y={day ? 61 : 65} textAnchor="middle" fill="currentColor" stroke="none" fontFamily="var(--serif)" fontStyle="italic" fontWeight="600" fontSize="17">{mark}</text>
      {day && <><path d="M40 67h40" strokeWidth=".7" />
        <text x="60" y="76" textAnchor="middle" fill="currentColor" stroke="none" fontFamily="var(--mono)" fontSize="6.4" letterSpacing=".6">{day}</text></>}
    </g>
  </svg>;
}

/**
 * The invigilator's view of the room: one desk per candidate, answer pips
 * filling as items are answered, status by word and shape as well as colour.
 * Reconnects show as a neutral observation tag, never as a warning.
 */
export function SeatingPlan({ roster }) {
  return <div className="res-room">
    <div className="res-room__front" aria-hidden="true"><span>Invigilator · front of room</span></div>
    <ol className="res-seats" aria-label="Seating plan">
      {roster.map((r, i) => {
        const meta = ATTEMPT_STATUS_META[r.status] ?? { label: r.status, glyph: "•" };
        return <li key={r.candidate_id} className={`res-desk res-desk--${r.status}`}>
          <span className="res-desk__no">Desk {two(i + 1)}</span>
          <strong className="res-desk__name">{r.display_name}</strong>
          <span className="res-desk__pips" aria-hidden="true">{pips(r.answered_count, r.total_items).map((on, n) => <i key={n} className={on ? "on" : ""} />)}</span>
          <span className="res-desk__state"><span aria-hidden="true">{meta.glyph} </span>{meta.label} · <span className="res-mono">{r.answered_count}/{r.total_items}</span></span>
          {r.incident_count > 0 && <span className="res-desk__obs">{r.incident_count} observation{r.incident_count > 1 ? "s" : ""} · no penalty</span>}
        </li>;
      })}
    </ol>
  </div>;
}

/** The examiner's mark, circled in red ink beside the script. */
export function RedPenMark({ awarded, cap }) {
  if (awarded === null || awarded === undefined) return null;
  return <span className="res-redpen" aria-hidden="true">
    <span className="res-redpen__value">{Number(awarded).toString()}</span><span className="res-redpen__cap">/{Number(cap).toString()}</span>
  </span>;
}

/** Quick-mark chips: one press puts a mark in the award field. */
export function MarkChips({ steps, value, onPick, disabled }) {
  return <div className="res-chips" role="group" aria-label="Quick marks">
    {steps.map(s => <button key={s} type="button" className="res-chip" disabled={disabled}
      aria-pressed={Number(value) === s && value !== ""} onClick={() => onPick(s.toFixed(2))}>{s % 1 ? s.toFixed(1) : s}</button>)}
  </div>;
}

/**
 * Dot plot of graded totals on a ruled 0..total axis. Equal scores stack.
 * Mean (▲) and median (◆) sit under the rule. The caption repeats it in words.
 */
export function ScoreStrip({ attempts, total, mean, median }) {
  const W = 640, L = 24, R = 616, Y = 74;
  const x = f => L + f * (R - L);
  const max = Number(total);
  const dots = stackScores(attempts.map(a => ({ score: a.total_score, label: a.display_name })), total);
  const pending = attempts.filter(a => a.total_score === null).length;
  const top = Math.min(40, Y - 26 - Math.max(0, ...dots.map(d => d.level)) * 15);
  const hasMean = mean !== null && mean !== undefined, hasMedian = median !== null && median !== undefined;
  const same = hasMean && hasMedian && Number(mean) === Number(median);
  return <figure className="res-strip">
    <svg viewBox={`0 ${top} ${W} ${Y + 48 - top}`} role="img" aria-label="Distribution of graded totals">
      <line x1={L} x2={R} y1={Y} y2={Y} className="res-strip__axis" />
      {axisTicks(total).map(t => <g key={t}>
        <line x1={x(t / max)} x2={x(t / max)} y1={Y} y2={Y + (t % 5 === 0 || t === max ? 7 : 4)} className="res-strip__tick" />
        {(t % 2 === 0 || t === max) && <text x={x(t / max)} y={Y + 19} className="res-strip__label">{t}</text>}
      </g>)}
      {dots.map((d, n) => <circle key={n} cx={x(d.fraction)} cy={Y - 10 - d.level * 15} r="6" className="res-strip__dot"><title>{`${d.label}: ${d.score.toFixed(2)}`}</title></circle>)}
      {hasMean && <g transform={`translate(${x(Number(mean) / max)} ${Y + 30})`}><path d="M0 -6 5.5 3.5H-5.5z" className="res-strip__mean" />
        <text y="15" className="res-strip__label res-strip__label--ink">{same ? `mean = median ${Number(mean).toFixed(2)}` : `mean ${Number(mean).toFixed(2)}`}</text></g>}
      {hasMedian && !same && <g transform={`translate(${x(Number(median) / max)} ${Y + 30})`}><path d="M0 -5 5 0 0 5 -5 0z" className="res-strip__median" />
        <text y="15" className="res-strip__label res-strip__label--ink">{`median ${Number(median).toFixed(2)}`}</text></g>}
    </svg>
    <figcaption className="res-muted">
      {dots.length ? <>{dots.length} graded {dots.length === 1 ? "total" : "totals"} on 0–{max}: {dots.map(d => `${d.label} ${d.score.toFixed(2)}`).join(", ")}.</> : "No graded totals yet."}
      {pending > 0 && <> {pending} awaiting grades, not plotted.</>}
    </figcaption>
  </figure>;
}

/** How the public check works, in three plain steps. */
export function VerifyExplainer() {
  return <aside className="res-howto" aria-labelledby="howto-title">
    <h2 id="howto-title">How verification works</h2>
    <ol>
      <li><span className="res-howto__no">01</span><div><strong>Your file stays here.</strong> The PDF is hashed with SHA-256 inside this browser. Its contents are never uploaded.</div></li>
      <li><span className="res-howto__no">02</span><div><strong>Two values travel.</strong> Only the verification code and the 64-character digest are sent to Folio.</div></li>
      <li><span className="res-howto__no">03</span><div><strong>One answer returns.</strong> Valid or not valid. No name, exam or score is ever disclosed, so anyone may check a report safely.</div></li>
    </ol>
    <p className="res-muted">Changing a single byte of the PDF changes its digest, so an edited report cannot pass.</p>
  </aside>;
}

/** A tear-off verification stub: perforation, code, grouped digest, stamp. */
export function VerificationStub({ code, digest, releasedAt, copied, onCopy, verifyHref, onVerify }) {
  return <section className="res-stub" aria-labelledby="stub-title">
    <div className="res-stub__perf" aria-hidden="true"><span>✂</span></div>
    <div className="res-stub__body">
      <div>
        <h2 id="stub-title" className="mini">Verification stub · keep with your report</h2>
        <p className="res-stub__code"><code>{code}</code>
          <button type="button" className="quiet" onClick={onCopy}>{copied ? "Copied" : "Copy code"}</button></p>
        <p className="mini res-stub__label">SHA-256 of the issued PDF</p>
        <p className="res-stub__digest" aria-label={`SHA-256 ${digest}`}>{digestGroups(digest).map((g, i) => <span key={i}>{g}</span>)}</p>
        <a className="res-stub__link" href={verifyHref} onClick={onVerify}>Verify this report →</a>
      </div>
      <Stamp mark="Released" legend="Folio · Examination office · Result released ·" date={releasedAt} className="res-stub__stamp" />
    </div>
  </section>;
}

/** The released score as a result slip: set figure, ruled mark bar, particulars. */
export function ResultSlip({ score, max, closeReason }) {
  const value = Number(score), cap = Number(max);
  const share = cap > 0 ? Math.min(Math.max(value / cap, 0), 1) : 0;
  const cells = cap > 0 && cap <= 20 && Number.isInteger(cap) ? cap : 10;
  return <div className="res-slip">
    <div className="res-slip__figure">
      <span className="mini">Released official score</span>
      <p><strong>{value.toFixed(2)}</strong><span className="res-slip__of">out of {cap.toFixed(2)}</span></p>
    </div>
    <div className="res-slip__rule" aria-hidden="true">
      <span className="res-slip__fill" style={{ width: `${share * 100}%` }} />
      {Array.from({ length: cells - 1 }, (_, i) => <i key={i} style={{ left: `${((i + 1) * 100) / cells}%` }} />)}
    </div>
    <dl className="res-slip__facts">
      <div><dt>Percentage</dt><dd>{Math.round(share * 100)}%</dd></div>
      <div><dt>Attempt</dt><dd>{closeReason === "expired" ? "Closed at deadline" : "Submitted"}</dd></div>
      <div><dt>Status</dt><dd>✓ Released and frozen</dd></div>
    </dl>
  </div>;
}
