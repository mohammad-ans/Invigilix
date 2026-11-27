import React, { useEffect, useRef, useState } from "react";
import { PageHead, SaveStatus } from "../../design/Folio.jsx";
import "../../design/folio.css";
import { request } from "./api.js";
import { AttemptSession } from "./session.js";
import { visibleItem } from "./queue.js";
export { purgeDeliveryAccount } from "./store.js";

const date = value => new Date(value).toLocaleString();
const answered = item => item.kind === "written" ? Boolean(item.written_answer.trim()) : item.selected_option_ids.length > 0;
const navigateTo = path => window.location.assign(path);

export function CandidateExams({ navigate = navigateTo }) {
  const [exams, setExams] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [version, retry] = useState(0);
  useEffect(() => {
    let active = true;
    setError("");
    request("/me/exams").then(list => active && setExams(list))
      .catch(() => active && setError("Could not load your exams."));
    return () => { active = false; };
  }, [version]);
  async function enter(exam) {
    setBusy(true);
    try {
      const attempt = await request("/exams/" + exam.id + "/attempts", "POST");
      navigate("/attempts/" + attempt.attempt_id);
    } catch {
      setError("Could not enter this exam. Refresh your assignments and try again.");
    } finally { setBusy(false); }
  }
  return <main className="shell"><PageHead crumb="Candidate workspace" title="My exams"/>
    {error && <p role="alert">{error} <button onClick={() => retry(version + 1)}>Refresh</button></p>}
    {!exams && !error && <p role="status">Loading assignments…</p>}
    {exams?.length === 0 && <p className="board">You have no assigned exams.</p>}
    {["available", "upcoming", "completed"].map(status => {
      const entries = exams?.filter(e => e.status === status);
      return entries?.length > 0 && <section className="board" key={status}>
        <h2>{status[0].toUpperCase() + status.slice(1)}</h2>
        {entries.map(e => <article className="event" key={e.id}><h3>{e.title}</h3>
          <p>{e.instructions}</p><p>{date(e.opens_at)} – {date(e.closes_at)}</p>
          {status === "available" && <button className="primary" disabled={busy} onClick={() => enter(e)}>
            {e.attempt_id ? "Resume attempt" : "Start exam"}</button>}
          {status === "completed" && (e.attempt_id
            ? <a href={"/attempts/" + e.attempt_id}>View receipt</a> : <span>Entry closed</span>)}
        </article>)}</section>;
    })}</main>;
}

function clock(ms) {
  const seconds = Math.max(0, Math.ceil(ms / 1000));
  return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
    .map(n => String(n).padStart(2, "0")).join(":");
}

function answerText(item) {
  if (item.kind === "written") return item.written_answer || "Unanswered";
  return item.options.filter(o => item.selected_option_ids.includes(o.id)).map(o => o.label).join(", ") || "Unanswered";
}

// Authoring can render this view with an in-memory controller and preview=true.
export function AttemptView({ state, session, preview = false }) {
  const [index, jump] = useState(0);
  const [review, setReview] = useState(false);
  const [tick, setTick] = useState(Date.now);
  const [prefBusy, setPrefBusy] = useState(false);
  const reviewHeading = useRef(null);
  const reviewButton = useRef(null);
  useEffect(() => {
    const timer = setInterval(() => setTick(Date.now()), 500);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => { if (review) reviewHeading.current?.focus(); }, [review]);
  const { record, receipt, error, outstanding = [] } = state;
  const remaining = record ? Date.parse(record.paper.deadline_at) - tick - record.offset : null;
  const elapsed = remaining !== null && remaining <= 0;
  useEffect(() => { if (elapsed) session.refresh(); }, [elapsed, session]);
  if (receipt) return <main className="shell"><PageHead crumb={preview ? "Preview" : "Candidate workspace"}
    title={receipt.close_reason === "expired" ? "Time expired" : "Attempt submitted"}/>
    <section className="board"><h2>Final receipt</h2><p>{date(receipt.finalized_at)}</p>
      <p>Attempt {receipt.attempt_id}</p>{outstanding.length > 0 && <p role="status">
        Local changes without confirmation for slots {outstanding.join(", ")}. Only accepted answers count.</p>}
    </section></main>;
  if (!record) return <main className="shell"><p role="status">{error || "Loading attempt…"}</p>
    {!state.denied && error && <button onClick={() => session.refresh()}>Retry</button>}</main>;
  const { paper, pending, conflicts } = record;
  const items = paper.items.map(i => visibleItem(record, i.slot));
  const item = items[index];
  const conflict = conflicts[item.slot];
  const prefs = paper.preferences;
  const locked = elapsed || state.submitting;
  const count = items.filter(answered).length;
  const status = preview ? "Saved in this preview" : state.storageFailed && state.status === "On this device"
    ? "Save failed" : state.status;
  function edit(patch) { session.edit(item, patch); }
  async function preference(patch) {
    setPrefBusy(true);
    try { await session.preferences({ ...prefs, ...patch }); }
    finally { setPrefBusy(false); }
  }
  function back() {
    setReview(false);
    requestAnimationFrame(() => reviewButton.current?.focus());
  }
  return <main className={"shell " + (prefs.workspace_layout === "focus" ? "focus" : "")}
    style={{ "--reading": prefs.font_percent / 100 + "rem", overflowWrap: "anywhere" }}>
    <PageHead crumb={preview ? "Examiner preview" : "Candidate workspace"} title={paper.title}
      details={<>{items.length} questions</>} aside={<div className="clock"><span className="clock-label">
        Time remaining</span><strong>{clock(remaining)}</strong></div>}/>
    {elapsed && <p role="status">Time is up. Waiting for the server receipt.</p>}
    {state.storageFailed && <p role="alert">Local storage unavailable. Unsaved work cannot be recovered after refresh.</p>}
    {error && <p role="alert">{error} <button onClick={() => session.refresh()}>Retry</button></p>}
    <div className="workgrid"><article className="sheet">
    {review ? <><h2 ref={reviewHeading} tabIndex={-1}>Review answers</h2>
      <p>{count} of {items.length} answered · {pending.length} pending edits</p>
      <ol className="review-list">{items.map((q, n) => <li key={q.slot}><button className="quiet"
        onClick={() => { jump(n); back(); }}>Question {q.display_no}</button> · {answerText(q)}
        {q.flagged && " · Flagged"}{conflicts[q.slot] && " · Conflict"}</li>)}</ol>
      <div className="actions"><button className="secondary" onClick={back}>Return to question</button>
        <button className="primary" disabled={locked} onClick={() => session.submit()}>Confirm submission</button></div>
    </> : <><div className="folio-line"><span className="qno">Question {item.display_no} / {items.length}</span>
      <button className={"flag " + (item.flagged ? "on" : "")} aria-pressed={item.flagged} disabled={locked}
        onClick={() => edit({ flagged: !item.flagged })}><i className="shape-flag"/>{item.flagged ? "Flagged" : "Flag for review"}</button></div>
      <h2 className="question" id="delivery-prompt">{item.prompt}</h2><p className="field-instruction">{item.max_marks} marks · {
        {single: "Select one answer", multiple: "Select all that apply", written: "Written response"}[item.kind]}</p>
      <fieldset disabled={locked} aria-labelledby="delivery-prompt">{item.kind === "written"
        ? <textarea aria-label="Your answer" style={{ fontSize: "var(--reading)" }} value={item.written_answer}
          onChange={e => edit({ written_answer: e.target.value })}/>
        : item.options.map(o => {
          const checked = item.selected_option_ids.includes(o.id);
          return <label key={o.id} className={"option " + (checked ? "chosen" : "")}>
            <input type={item.kind === "multiple" ? "checkbox" : "radio"} name="delivery-choice" checked={checked}
              onChange={() => edit({ selected_option_ids: item.kind === "single" ? [o.id] :
                checked ? item.selected_option_ids.filter(id => id !== o.id) : [...item.selected_option_ids, o.id] })}/>{o.label}</label>;
        })}</fieldset>
      {conflict && <section role="alert"><h3>Answer conflict</h3><p>Server answer: {answerText(conflict)} · {conflict.flagged ? "Flagged" : "Unflagged"}</p>
        <p>Your draft: {answerText(item)} · {item.flagged ? "Flagged" : "Unflagged"}</p>
        <button disabled={locked} onClick={() => session.resolve(item.slot, true)}>Keep my draft</button>
        <button disabled={locked} onClick={() => session.resolve(item.slot, false)}>Use server answer</button></section>}
      <div className="actions"><button className="quiet" disabled={locked || !answered(item)}
        onClick={() => edit(item.kind === "written" ? { written_answer: "" } : { selected_option_ids: [] })}>Clear answer</button>
        <button className="secondary" disabled={!index} onClick={() => jump(index - 1)}>Previous</button>
        <button className="primary" onClick={() => index + 1 === items.length ? setReview(true) : jump(index + 1)}>
          {index + 1 === items.length ? "Review answers" : "Next question"}</button></div></>}
      <SaveStatus state={status === "Save failed" ? "error" : pending.length ? "pending" : "saved"}>{status}</SaveStatus>
    </article><aside><section className="side"><div className="side-head"><h2>Answer sheet</h2>
      <div className="progress-top">Answered <span>{count} / {items.length}</span></div>
      <div className="track"><span style={{ width: 100 * count / items.length + "%" }}/></div></div>
      <div className="side-content"><nav className="numbers" aria-label="Questions">{items.map((q, n) =>
        <button key={q.slot} aria-current={index === n ? "step" : undefined}
          aria-label={`Question ${q.display_no}, ${answered(q) ? "answered" : "unanswered"}${q.flagged ? ", flagged" : ""}`}
          className={["number", answered(q) && "answered", index === n && "current", q.flagged && "flagged"].filter(Boolean).join(" ")}
          onClick={() => { jump(n); setReview(false); }}>{q.display_no}{answered(q) && <span className="done-mark">✓</span>}</button>)}</nav>
        <button ref={reviewButton} className="secondary block" onClick={() => setReview(true)}>Review answers</button></div></section>
      <div className="tools"><details><summary>Scratchpad</summary><div className="tool-body">
        <label>Private rough work<textarea key={paper.attempt_id} disabled={locked} defaultValue={record.scratch}
          onChange={e => session.scratch(e.target.value)}/></label></div></details>
      <details><summary>Workspace settings</summary><div className="tool-body prefs">
        <label>Text size <select disabled={prefBusy} value={prefs.font_percent}
          onChange={e => preference({ font_percent: Number(e.target.value) })}>
          {Array.from({length:121}, (_,i) => 80+i).map(n => <option key={n} value={n}>{n}%</option>)}</select></label>
        <label><input type="checkbox" disabled={prefBusy} checked={prefs.workspace_layout === "focus"}
          onChange={e => preference({ workspace_layout: e.target.checked ? "focus" : "standard" })}/> Focus layout</label>
        {state.preferenceError && <p role="alert">{state.preferenceError}</p>}</div></details></div></aside></div></main>;
}

function LiveAttempt({ accountId, attemptId }) {
  const [state, setState] = useState({});
  const [session, setSession] = useState(null);
  useEffect(() => {
    const model = new AttemptSession(accountId, attemptId, setState);
    setSession(model);
    model.init();
    const refresh = () => { if (!model.state.denied) model.refresh(); };
    const interval = setInterval(refresh, 15000);
    window.addEventListener("online", refresh);
    return () => {
      model.active = false;
      clearInterval(interval);
      window.removeEventListener("online", refresh);
    };
  }, [accountId, attemptId]);
  return session && <AttemptView state={state} session={session}/>;
}

export function CandidateAttempt(props) {
  return <LiveAttempt key={JSON.stringify([props.accountId, props.attemptId])} {...props}/>;
}
