import React, { useEffect, useState } from "react";
import { formatDate, formatDuration, formatMarks, letter } from "../domain/format.js";

/**
 * A printable galley proof of the paper, laid out the way candidates read a
 * printed exam: candidate box, instructions, hanging question numbers,
 * bracketed marks on a dotted leader, ruled answer space. "With key" adds the
 * mark scheme (keys and rubrics) and so carries a stronger watermark.
 * Rendered only in print (see .au-proof-sheet in authoring.css).
 */
export function ProofSheet({ exam, withKey }) {
  return <section className={`au-proof-sheet${withKey ? " au-proof-sheet--key" : ""}`} aria-hidden="true">
    <div className="au-proof-sheet__mark">{withKey ? "Mark scheme · Confidential" : "Proof · Not for candidates"}</div>
    <header className="au-proof-sheet__head">
      <span className="au-proof-sheet__office">Folio · Examination office</span>
      <h1>{exam.title}</h1>
      <p>{formatDuration(exam.duration_minutes)} · {formatMarks(exam.total_marks)} marks · {exam.items.length} questions</p>
      <p>{formatDate(exam.opens_at, { withZone: true })} – {formatDate(exam.closes_at)}</p>
    </header>
    <div className="au-proof-sheet__candidate">
      <span>Candidate name<i /></span><span>Candidate number<i /></span>
    </div>
    {exam.instructions && <div className="au-proof-sheet__instructions"><b>Instructions to candidates</b><p>{exam.instructions}</p></div>}
    <ol className="au-proof-sheet__questions">
      {exam.items.map((item, n) => {
        const v = item.version;
        return <li key={item.slot}>
          <span className="au-proof-sheet__no">{n + 1}</span>
          <div>
            <p className="au-proof-sheet__prompt"><span>{v.prompt}</span><span className="au-proof-sheet__leader" /><b>[{formatMarks(item.max_marks)}]</b></p>
            {v.kind !== "written" && <p className="au-proof-sheet__how">{v.kind === "multiple" ? "Select all that apply." : "Select one answer."}</p>}
            {v.kind === "written"
              ? <div className="au-proof-sheet__lines">{Array.from({ length: 6 }, (_, i) => <i key={i} />)}</div>
              : <ul className="au-proof-sheet__options">{v.options.map((o, i) => <li key={o.id} className={withKey && o.correct ? "is-key" : ""}>
                  <span className="au-proof-sheet__box">{withKey && o.correct ? "✓" : ""}</span><b>{letter(i)}</b> {o.label}</li>)}</ul>}
            {withKey && <div className="au-proof-sheet__scheme">
              <b>Mark scheme · v{v.number}</b>
              {v.kind === "written" ? <p>{v.rubric || "Examiner judgement; no rubric recorded."}</p>
                : <p>Key {v.options.map((o, i) => o.correct ? letter(i) : null).filter(Boolean).join(", ")} · {v.marking_rule === "partial_no_wrong" ? "partial credit, zero for any wrong choice" : "exact match"}</p>}
            </div>}
          </div>
        </li>;
      })}
    </ol>
    <footer className="au-proof-sheet__foot">
      <span>Printed {new Date().toLocaleString()}</span>
      <span>Versions {exam.items.map(i => `${i.slot}·v${i.version.number}`).join("  ")}</span>
      <span>{exam.published_at ? "Frozen paper" : "Draft — subject to change"}</span>
    </footer>
  </section>;
}

/** Hook: print the proof sheet, with or without the key, then tidy up. */
export function useProofPrint() {
  const [withKey, setWithKey] = useState(null);
  useEffect(() => {
    if (withKey === null) return undefined;
    document.body.classList.add("au-printing");
    const done = () => { document.body.classList.remove("au-printing"); setWithKey(null); };
    window.addEventListener("afterprint", done, { once: true });
    const t = setTimeout(() => window.print(), 30);
    return () => { clearTimeout(t); window.removeEventListener("afterprint", done); document.body.classList.remove("au-printing"); };
  }, [withKey]);
  return [withKey, setWithKey];
}
