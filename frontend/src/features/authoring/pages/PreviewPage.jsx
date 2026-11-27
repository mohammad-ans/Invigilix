import React, { useEffect, useRef, useState } from "react";
import { PageHead, SaveStatus } from "../../../design/Folio.jsx";
import { paths } from "../paths.js";
import { useResource } from "../hooks.js";
import { formatMarks, letter, two } from "../domain/format.js";
import { Dialog } from "../components/instruments.jsx";
import { EmptyState, Loading, LoadError } from "../components/primitives.jsx";

const answered = item => (item.kind === "written" ? item.written_answer.trim() !== "" : item.selected_option_ids.length > 0);
const clock = ms => { const s = Math.max(0, Math.ceil(ms / 1000)); return `${two(Math.floor(s / 60))}:${two(s % 60)}`; };

/**
 * /examiner/exams/:id/preview — the sandbox (SR03).
 * The paper comes from POST /exams/:id/preview, which writes nothing. Answers,
 * flags, the timer and the submission live only in this component's memory and
 * vanish when the examiner leaves. No attempt, grade, incident or report exists.
 */
export default function PreviewPage({ api, params, navigate }) {
  const sandbox = useResource(() => api.previewExam(params.id), [api, params.id]);
  const [session, setSession] = useState(null);

  useEffect(() => {
    if (!sandbox.data) return;
    const { server_time, deadline_at, items } = sandbox.data;
    setSession({ items: items.map(i => ({ ...i })), current: 0, ends: Date.now() + (Date.parse(deadline_at) - Date.parse(server_time)), receipt: null, scratch: "", size: 100 });
  }, [sandbox.data]);

  if (sandbox.error) return <main className="shell au-page"><LoadError error={sandbox.error} retry={sandbox.reload} /></main>;
  if (!sandbox.data || !session) return <main className="shell au-page"><Loading label="Preparing the sandbox" /></main>;
  const restart = () => sandbox.reload();
  return <Workspace paper={sandbox.data} session={session} setSession={setSession} restart={restart}
    exit={() => navigate(paths.edit(params.id))} crumbs={{ exams: () => navigate(paths.exams), edit: () => navigate(paths.edit(params.id)) }} />;
}

function Workspace({ paper, session, setSession, restart, exit, crumbs }) {
  const [now, setNow] = useState(Date.now());
  const [reviewing, setReviewing] = useState(false);
  const total = session.items.length;
  const closed = Boolean(session.receipt);
  const remaining = session.ends - now;
  const patch = fields => setSession(s => ({ ...s, ...fields }));
  const updateItem = (index, fields) => setSession(s => s.receipt ? s : ({ ...s, items: s.items.map((it, n) => n === index ? { ...it, ...fields, revision: it.revision + 1 } : it) }));
  const finish = reason => setSession(s => s.receipt ? s : ({ ...s, receipt: { reason, at: new Date(), answered: s.items.filter(answered).length, flagged: s.items.filter(i => i.flagged).length, scratch: "" }, scratch: "" }));

  useEffect(() => {
    if (closed) return undefined;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [closed]);
  useEffect(() => { if (!closed && remaining <= 0) finish("expired"); }, [remaining, closed]); // eslint-disable-line react-hooks/exhaustive-deps

  const warning = remaining <= 5 * 60 * 1000 && !closed;
  return <>
    <div className="au-sandbox-strip" role="note">
      <div className="au-sandbox-strip__inner">
        <span className="au-sandbox-strip__tag">Sandbox</span>
        <span><b>Preview as a candidate.</b> Nothing here is recorded: no attempt, grade, incident, report or statistic.</span>
        <button className="secondary" onClick={exit}>Exit preview</button>
      </div>
    </div>
    <main className="shell au-page" style={{ "--reading": session.size / 100 + "rem" }}>
      <PageHead crumb={<><a href="#exams" onClick={e => { e.preventDefault(); crumbs.exams(); }}>Exam register</a> <span aria-hidden="true">/</span> <a href="#edit" onClick={e => { e.preventDefault(); crumbs.edit(); }}>{paper.title}</a> <span aria-hidden="true">/</span> Preview</>}
        title={paper.title} details={<><b>Preview</b><i />{total} {total === 1 ? "question" : "questions"}<i />{formatMarks(paper.total_marks)} marks</>}
        aside={total > 0 && <div className={`clock${warning ? " au-clock--warn" : ""}`} role="timer" aria-live="off">
          <span className="clock-label">Time remaining · preview</span><strong>{closed ? "--:--" : clock(remaining)}</strong>
          {warning && <span className="sr-only" aria-live="assertive">Less than five minutes remain in this preview.</span>}</div>} />

      {paper.instructions && <details className="au-instructions"><summary>Instructions shown to candidates</summary><p>{paper.instructions}</p></details>}
      {total === 0 ? <EmptyState title="This paper has no questions yet" action={<button className="primary" onClick={exit}>Back to the editor</button>}>Add questions from the bank, then preview again.</EmptyState>
        : closed ? <Receipt receipt={session.receipt} total={total} restart={restart} exit={exit} />
        : <Sheet session={session} paper={paper} patch={patch} updateItem={updateItem} review={() => setReviewing(true)} />}
    </main>
    {reviewing && <Dialog title="Review submission" onClose={() => setReviewing(false)}>
      <p>{session.items.filter(answered).length} of {total} answered · {session.items.filter(i => i.flagged).length} flagged for review.</p>
      <ol className="review-list">{session.items.map((it, n) => <li key={it.slot} className="split"><button className="au-link" onClick={() => { patch({ current: n }); setReviewing(false); }}>Question {two(n + 1)}</button>
        <span>{answered(it) ? "Answered" : "Unanswered"}{it.flagged ? " · Flagged" : ""}</span></li>)}</ol>
      <div className="actions"><button className="secondary" onClick={() => setReviewing(false)}>Return to preview</button>
        <button className="primary" data-autofocus onClick={() => { finish("submitted"); setReviewing(false); }}>Submit sandbox attempt</button></div>
    </Dialog>}
  </>;
}

function Sheet({ session, paper, patch, updateItem, review }) {
  const i = session.current, item = session.items[i], total = session.items.length;
  const headingRef = useRef(null);
  useEffect(() => { headingRef.current?.focus({ preventScroll: true }); }, [i]);
  const done = session.items.filter(answered).length;
  const instruction = item.kind === "written" ? "Written response" : item.kind === "multiple" ? "Select all that apply" : "Select one answer";
  function choose(id) {
    const chosen = item.selected_option_ids;
    updateItem(i, { selected_option_ids: item.kind === "multiple" ? (chosen.includes(id) ? chosen.filter(x => x !== id) : [...chosen, id]) : [id] });
  }
  return <div className="workgrid">
    <article className="sheet">
      <div className="folio-line"><span className="qno">Question {two(i + 1)} / {two(total)}</span>
        <button className={"flag " + (item.flagged ? "on" : "")} aria-pressed={item.flagged} onClick={() => updateItem(i, { flagged: !item.flagged })}><i className="shape-flag" />{item.flagged ? "Flagged" : "Flag for review"}</button></div>
      <h2 className="question" id="question-title" tabIndex={-1} ref={headingRef}>{item.prompt}</h2>
      <fieldset aria-labelledby="question-title"><legend className="field-instruction">{instruction} · {formatMarks(item.max_marks)} marks</legend>
        {item.kind === "written"
          ? <textarea aria-label="Written response" rows={6} value={item.written_answer} onChange={e => updateItem(i, { written_answer: e.target.value })} />
          : item.options.map((o, n) => <label key={o.id} className={"option " + (item.selected_option_ids.includes(o.id) ? "chosen" : "")}>
            <input type={item.kind === "multiple" ? "checkbox" : "radio"} name={"answer-" + item.slot} checked={item.selected_option_ids.includes(o.id)} onChange={() => choose(o.id)} />
            <span className="opt-letter">{letter(n)}</span>{o.label}</label>)}
      </fieldset>
      <div className="actions"><SaveStatus state="saved">Saved in this preview</SaveStatus>
        <div className="row"><button className="secondary" disabled={i === 0} onClick={() => patch({ current: i - 1 })}>Previous</button>
          <button className="primary" onClick={() => (i === total - 1 ? review() : patch({ current: i + 1 }))}>{i === total - 1 ? "Review answers" : "Next question →"}</button></div></div>
    </article>
    <aside>
      <section className="side" aria-label="Answer sheet"><div className="side-head"><h2>Answer sheet</h2>
        <div className="progress-top"><span>Answered</span><span className="progress-count">{two(done)} / {two(total)}</span></div>
        <div className="track" aria-hidden="true"><span style={{ width: (100 * done / total) + "%" }} /></div></div>
        <div className="side-content"><div className="numbers">{session.items.map((it, n) => {
          const a = answered(it);
          return <button key={it.slot} aria-current={n === i ? "step" : undefined} aria-label={`Question ${n + 1}, ${a ? "answered" : "unanswered"}${it.flagged ? ", flagged" : ""}`}
            className={["number", a ? "answered" : "", it.flagged ? "flagged" : "", n === i ? "current" : ""].join(" ")} onClick={() => patch({ current: n })}>{two(n + 1)}{a && <span aria-hidden="true" className="done-mark">✓</span>}</button>;
        })}</div>
        <div className="legend"><span><i className="key done" />Answered ✓</span><span><i className="key open" />Open</span><span><i className="shape-flag" />Flagged</span></div>
        <button className="secondary block" onClick={review}>Review submission</button></div>
      </section>
      <div className="tools">
        <details><summary>Scratchpad</summary><div className="tool-body"><label>Private rough work<textarea value={session.scratch} onChange={e => patch({ scratch: e.target.value })} /></label></div></details>
        <details><summary>Workspace settings</summary><div className="tool-body"><div className="prefs"><label>Text size <select value={session.size} onChange={e => patch({ size: Number(e.target.value) })}>{[80, 100, 125, 150, 200].map(n => <option key={n} value={n}>{n}%</option>)}</select></label></div></div></details>
      </div>
      {(paper.items.length > 1) && <p className="au-sub au-shuffle-note">Shown in slot order. If shuffling is on, each candidate sees their own fixed order.</p>}
    </aside>
  </div>;
}

function Receipt({ receipt, total, restart, exit }) {
  const ref = useRef(null);
  useEffect(() => { ref.current?.focus(); }, []);
  return <section className="sheet au-receipt" tabIndex={-1} ref={ref} aria-labelledby="receipt-title">
    <div className="folio-line"><span className="qno">Sandbox receipt</span><span className="au-receipt__void" aria-hidden="true">Not recorded</span></div>
    <h2 id="receipt-title" className="question">{receipt.reason === "expired" ? "Time expired in the preview" : "Sandbox submission complete"}</h2>
    <dl className="au-record">
      <div><dt>Close reason</dt><dd>{receipt.reason === "expired" ? "Expired at the preview deadline" : "Submitted"}</dd></div>
      <div><dt>Answered</dt><dd className="au-mono">{receipt.answered} / {total}</dd></div>
      <div><dt>Flagged</dt><dd className="au-mono">{receipt.flagged}</dd></div>
      <div><dt>Finished</dt><dd className="au-mono">{receipt.at.toLocaleTimeString()}</dd></div>
    </dl>
    <p className="au-sub">These answers were discarded. Real attempt counts, grades, incidents, reports and analytics are exactly as they were before this preview.</p>
    <div className="actions"><span /><div className="row"><button className="secondary" onClick={restart}>Restart preview</button><button className="primary" onClick={exit}>Back to the editor</button></div></div>
  </section>;
}
