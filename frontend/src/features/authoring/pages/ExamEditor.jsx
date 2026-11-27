import React, { useEffect, useMemo, useRef, useState } from "react";
import { PageHead, SaveStatus } from "../../../design/Folio.jsx";
import { paths } from "../paths.js";
import { useResource } from "../hooks.js";
import { groupIssues, parseMarks, tally } from "../domain/rules.js";
import { RULE, formatDate, formatDuration, formatMarks, formatWindow, two } from "../domain/format.js";
import { Checklist, Dialog, FrozenSeal, MarkLedger } from "../components/instruments.jsx";
import { ExamForm } from "../components/ExamForm.jsx";
import {
  Banner, DifficultyScale, ErrorSummary, KindTag, Loading, LoadError, ModeLabel, StateBadge, VersionTag,
} from "../components/primitives.jsx";
import { BankPicker } from "../components/BankPicker.jsx";
import { PaperProfile, WindowTimeline } from "../components/insights.jsx";

const toDraft = items => items.map(i => ({
  question_id: i.question_id, version_id: i.version.id, max_marks: i.max_marks, version: i.version,
  latest_version_number: i.latest_version_number,
}));

/** /examiner/exams/:id/edit — draft editor and frozen-paper review (FR03–FR05). */
export default function ExamEditor({ api, params, navigate }) {
  const exam = useResource(() => api.getExam(params.id), [api, params.id]);
  const [copying, setCopying] = useState(false);
  const copiedFrom = new URLSearchParams(window.location.search || window.location.hash.split("?")[1] || "").get("copied");
  const [items, setItems] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [detailsDirty, setDetailsDirty] = useState(false);
  const [saveState, setSaveState] = useState({ state: "saved", text: "" });
  const [itemError, setItemError] = useState(null);
  const [picking, setPicking] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [publishError, setPublishError] = useState(null);
  const [justPublished, setJustPublished] = useState(false);
  const slotRefs = useRef({});

  useEffect(() => { if (exam.data && !dirty) setItems(toDraft(exam.data.items)); }, [exam.data]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!dirty && !detailsDirty) return undefined;
    const warn = e => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, detailsDirty]);

  const data = exam.data;
  const frozen = Boolean(data?.published_at);
  const slots = useMemo(() => (items ?? []).map((i, n) => ({ ...i, slot: n + 1 })), [items]);
  const ledger = tally(slots, data?.total_marks);
  const itemIssues = groupIssues(itemError?.issues, "item");

  function edit(next) { setItems(next); setDirty(true); setSaveState({ state: "pending", text: "Unsaved paper changes" }); setItemError(null); }
  const move = (index, delta) => { const next = [...items]; const [it] = next.splice(index, 1); next.splice(index + delta, 0, it); edit(next); };

  async function saveParticulars(details) {
    setSaveState({ state: "pending", text: "Saving" });
    try { exam.replace(await api.updateExam(data.id, details)); setSaveState({ state: "saved", text: "Particulars saved on server" }); }
    catch (e) { setSaveState({ state: "error", text: "Save failed" }); throw e; }
  }

  async function savePaper() {
    setSaveState({ state: "pending", text: "Saving" });
    try {
      const updated = await api.setItems(data.id, slots.map(s => ({ question_id: s.question_id, version_id: s.version_id, max_marks: String(s.max_marks).trim() })));
      setDirty(false); exam.replace(updated); setItems(toDraft(updated.items));
      setSaveState({ state: "saved", text: "Paper saved on server" });
    } catch (e) {
      setItemError(e.issues?.length ? e : { message: e.message, issues: [] });
      setSaveState({ state: "error", text: "Save failed" });
    }
  }

  async function publish() {
    setPublishError(null);
    try { exam.replace(await api.publishExam(data.id)); setConfirming(false); setJustPublished(true); }
    catch (e) { setPublishError(e); }
  }

  function jump(slot) {
    const el = slotRefs.current[slot];
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
    el?.querySelector("input, button")?.focus({ preventScroll: true });
  }

  if (exam.error) return <main className="shell au-page"><LoadError error={exam.error} retry={exam.reload} /></main>;
  if (!data || !items) return <main className="shell au-page"><Loading label="Opening the exam" /></main>;

  const failing = data.publication.checks.filter(c => !c.passed).length;
  return <main className="shell au-page">
    <PageHead crumb={<><a href={paths.exams} onClick={e => { e.preventDefault(); navigate(paths.exams); }}>Exam register</a> <span aria-hidden="true">/</span> {frozen ? "Review" : "Edit draft"}</>}
      title={data.title}
      details={<><StateBadge state={data.state} /><i />{formatWindow(data.opens_at, data.closes_at)}<i />{formatDuration(data.duration_minutes)}<i />{formatMarks(data.total_marks)} marks<ModeLabel mode={api.mode} /></>}
      aside={<div className="row au-head-actions">
        <button className="secondary" onClick={() => navigate(paths.enrollment(data.id))}>Roster</button>
        <button className="secondary" disabled={copying} onClick={async () => {
          setCopying(true);
          try { const copy = await api.duplicateExam(data.id); navigate(paths.edit(copy.id) + "?copied=1"); }
          finally { setCopying(false); }
        }}>{copying ? "Copying…" : "Copy to new draft"}</button>
        <button className="secondary" onClick={() => navigate(paths.preview(data.id))}>Preview as candidate</button>
      </div>} />

    {copiedFrom && !frozen && <Banner tone="ok" title="New draft copied">Particulars and pinned question versions were copied; the roster was not. Set a new window, then re-pin any slot whose bank question now has a newer version.</Banner>}
    {justPublished && <Banner tone="ok" title="Published">The paper is frozen. Enrolled candidates can see its instructions now and start it when the window opens.</Banner>}
    {frozen ? <FrozenSeal publishedAt={data.published_at} itemCount={data.items.length} />
      : ledger.balanced || !items.length ? <Banner tone="info" title="Editable draft">Candidates cannot see this exam. Changes save to the draft until you publish.</Banner>
      : <Banner tone="error" mark="≠" title="Marks do not add up">
          Slots allocate {formatMarks(ledger.allocated / 100)} of the declared {formatMarks(ledger.declared / 100)}. Adjust a slot’s marks or the declared total before publishing.
        </Banner>}

    <div className="workgrid au-editor">
      <div className="au-editor__main">
        <article className="sheet au-section" aria-labelledby="paper-title">
          <div className="folio-line"><span className="qno">Paper · {two(slots.length)} {slots.length === 1 ? "slot" : "slots"}</span>
            {!frozen && <SaveStatus state={saveState.state}>{saveState.text || "Paper saved on server"}</SaveStatus>}</div>
          <h2 id="paper-title" className="au-h2">Questions in order</h2>
          {!frozen && <ErrorSummary error={itemError} title="Some slots need attention" describe={i => <>{i.item ? <b>Slot {two(i.item)} · </b> : null}{i.message}</>} />}

          {slots.length === 0 && <div className="au-slot-empty"><p>No questions yet. Add them from your bank; each slot pins the version you choose.</p></div>}
          <ol className="au-slots">{slots.map((s, index) => {
            const issues = itemIssues.get(s.slot) ?? [];
            const marksIssue = !frozen ? parseMarks(s.max_marks).issue : null;
            const outdated = s.latest_version_number > s.version.number;
            return <li key={s.question_id} className={`au-slot${issues.length ? " au-slot--invalid" : ""}`} ref={el => { slotRefs.current[s.slot] = el; }}>
              <span className="au-slot__no" aria-hidden="true">{two(s.slot)}</span>
              <div className="au-slot__body">
                <p className="au-slot__prompt"><span className="sr-only">Slot {s.slot}: </span>{s.version.prompt}</p>
                <div className="au-slot__meta"><KindTag kind={s.version.kind} /><span>{s.version.topic}</span><DifficultyScale level={s.version.difficulty} /><VersionTag number={s.version.number} latest={s.latest_version_number} /><span className="au-sub">{RULE[s.version.marking_rule]}</span></div>
                {outdated && <p className="au-slot__note"><span aria-hidden="true">◷ </span>Pinned to v{s.version.number}; the bank now has v{s.latest_version_number}.
                  {!frozen && <> <BankUpgrade api={api} slot={s} onUpgrade={version => edit(items.map((x, n) => n === index ? { ...x, version_id: version.id, version, latest_version_number: version.number } : x))} /></>}</p>}
                {issues.map((i, n) => <p key={n} className="au-field__error"><b aria-hidden="true">✕</b> {i.message}</p>)}
              </div>
              <div className="au-slot__marks">
                {frozen ? <span className="au-mono au-slot__cap">{formatMarks(s.max_marks)}<small>marks</small></span>
                  : <label><span className="au-field__label">Marks</span>
                    <input inputMode="decimal" value={s.max_marks} aria-invalid={marksIssue ? true : undefined}
                      onChange={e => edit(items.map((x, n) => n === index ? { ...x, max_marks: e.target.value } : x))} aria-label={`Marks for slot ${s.slot}`} />
                    {marksIssue && <span className="au-field__error">{marksIssue.message}</span>}</label>}
                {!frozen && <div className="au-slot__tools">
                  <button type="button" className="au-icon" disabled={index === 0} onClick={() => move(index, -1)} aria-label={`Move slot ${s.slot} up`}>↑</button>
                  <button type="button" className="au-icon" disabled={index === slots.length - 1} onClick={() => move(index, 1)} aria-label={`Move slot ${s.slot} down`}>↓</button>
                  <button type="button" className="au-icon au-icon--remove" onClick={() => edit(items.filter((_, n) => n !== index))} aria-label={`Remove slot ${s.slot}`}>×</button>
                </div>}
              </div>
            </li>;
          })}</ol>

          {!frozen && <div className="actions">
            <button type="button" className="secondary" onClick={() => setPicking(true)}><span aria-hidden="true">＋</span> Add from bank</button>
            <div className="row">
              {dirty && <button type="button" className="quiet" onClick={() => { setItems(toDraft(data.items)); setDirty(false); setItemError(null); setSaveState({ state: "saved", text: "Changes discarded" }); }}>Discard changes</button>}
              <button type="button" className="primary" disabled={!dirty} onClick={savePaper}>Save paper</button>
            </div>
          </div>}
        </article>

        <article className="sheet au-section" aria-labelledby="particulars-title">
          <div className="folio-line"><span className="qno">Particulars</span>{detailsDirty && <SaveStatus state="pending">Unsaved particulars</SaveStatus>}</div>
          <h2 id="particulars-title" className="au-h2">{frozen ? "Frozen schedule and settings" : "Title, window and marking"}</h2>
          {frozen && <WindowTimeline opens={data.opens_at} closes={data.closes_at} duration={data.duration_minutes} />}
          {frozen ? <dl className="au-record">
            <div><dt>Instructions</dt><dd>{data.instructions || "—"}</dd></div>
            <div><dt>Opens</dt><dd className="au-mono">{formatDate(data.opens_at, { withZone: true })}</dd></div>
            <div><dt>Closes</dt><dd className="au-mono">{formatDate(data.closes_at, { withZone: true })}</dd></div>
            <div><dt>Duration</dt><dd>{formatDuration(data.duration_minutes)} per attempt, capped at closing</dd></div>
            <div><dt>Declared total</dt><dd className="au-mono">{formatMarks(data.total_marks)}</dd></div>
            <div><dt>Shuffle</dt><dd>{[data.shuffle_questions && "Question order", data.shuffle_choices && "Choice order"].filter(Boolean).join(" · ") || "None"}</dd></div>
          </dl> : <ExamForm key={data.id} initial={data} submitLabel="Save particulars" onSubmit={saveParticulars} onDirty={setDetailsDirty} />}
        </article>
      </div>

      <aside className="au-editor__side">
        <section className="side">
          <div className="side-head"><h2>Allocation</h2></div>
          <div className="side-content"><MarkLedger items={slots} totalMarks={data.total_marks} /></div>
        </section>
        <section className="side">
          <details className="au-profile-card" open>
            <summary><h2>Paper profile</h2></summary>
            <div className="side-content"><PaperProfile slots={slots} /></div>
          </details>
        </section>
        {!frozen && <section className="side">
          <div className="side-content">
            <Checklist publication={data.publication} onJump={jump} />
            {dirty && <p className="au-sub au-warn"><span aria-hidden="true">! </span>Save the paper to update this check.</p>}
            <button className="primary block au-publish" disabled={!data.publication.ready || dirty || detailsDirty} onClick={() => setConfirming(true)}>Publish paper</button>
            <p className="au-sub" id="publish-note">{dirty || detailsDirty ? "Save your changes first." : failing ? `Resolve ${failing} ${failing === 1 ? "check" : "checks"} to publish.` : "Publishing freezes the paper. It cannot be undone."}</p>
          </div>
        </section>}
        {frozen && <section className="side"><div className="side-content au-pins">
          <h3 className="au-subhead">Pinned versions</h3>
          <ul>{data.items.map(i => <li key={i.slot}><span className="au-mono">{two(i.slot)}</span> v{i.version.number} <span className="au-sub">· {formatMarks(i.max_marks)} marks</span></li>)}</ul>
        </div></section>}
      </aside>
    </div>

    {picking && <BankPicker api={api} onClose={() => setPicking(false)} exclude={new Set(items.map(i => i.question_id))}
      onPick={question => { edit([...items, { question_id: question.id, version_id: question.latest.id, version: question.latest, latest_version_number: question.version_count, max_marks: "1.00" }]); }} />}

    {confirming && <Dialog title="Publish this paper?" onClose={() => setConfirming(false)}>
      <ErrorSummary error={publishError} title="The server refused publication" describe={i => <>{i.item ? <b>Slot {two(i.item)} · </b> : null}{i.message}</>} />
      <p>Publishing freezes <b>{data.items.length} slots</b>, their question versions, <b>{formatMarks(data.total_marks)} marks</b>, the window and shuffle settings. Enrolled candidates will see the title and instructions.</p>
      <p className="au-sub">You cannot edit or unpublish afterwards. Later bank edits create new versions and leave this paper unchanged.</p>
      <div className="actions"><span /><div className="row">
        <button className="secondary" onClick={() => setConfirming(false)}>Keep editing</button>
        <button className="primary" data-autofocus onClick={publish}>Publish and freeze</button></div></div>
    </Dialog>}
  </main>;
}

/** Offer to re-pin a slot to the bank's latest version (draft only). */
function BankUpgrade({ api, slot, onUpgrade }) {
  const [busy, setBusy] = useState(false);
  return <button type="button" className="au-link" disabled={busy} onClick={async () => {
    setBusy(true);
    try { const q = await api.getQuestion(slot.question_id); onUpgrade(q.versions[0]); } finally { setBusy(false); }
  }}>Use v{slot.latest_version_number}</button>;
}
