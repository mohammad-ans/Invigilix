import React, { useState } from "react";
import { PageHead } from "../../../design/Folio.jsx";
import { paths } from "../paths.js";
import { useResource } from "../hooks.js";
import { formatWindow, two } from "../domain/format.js";
import { TrayArt } from "../components/illustrations.jsx";
import { parseEmailList, usable } from "../domain/emails.js";
import { ImportPanel } from "../components/ImportPanel.jsx";
import {
  AccessBadge, Banner, EmptyState, ErrorSummary, Field, Loading, LoadError, ModeLabel, StateBadge, Stat,
} from "../components/primitives.jsx";

const BLOCKED = new Set(["account_disabled", "not_candidate"]);

/** /examiner/exams/:id/enrollment — scoped roster, entry status and CSV import (FR06, SR04). */
export default function RosterPage({ api, params, navigate }) {
  const exam = useResource(() => api.getExam(params.id), [api, params.id]);
  const roster = useResource(() => api.getRoster(params.id), [api, params.id]);
  const [emails, setEmails] = useState("");
  const [enrollError, setEnrollError] = useState(null);
  const [pending, setPending] = useState(false);
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState(null);
  const [mode, setMode] = useState("type");

  if (exam.error || roster.error) return <main className="shell au-page"><LoadError error={exam.error ?? roster.error} retry={() => { exam.reload(); roster.reload(); }} /></main>;
  if (!exam.data || !roster.data) return <main className="shell au-page"><Loading label="Opening the roster" /></main>;

  const closed = roster.data.state === "completed";
  const entries = roster.data.entries;
  const shown = entries.filter(e => `${e.display_name} ${e.email}`.toLowerCase().includes(query.trim().toLowerCase()));
  const active = entries.filter(e => e.active);
  const tokens = parseEmailList(emails);
  const list = usable(tokens);
  const flawed = tokens.filter(t => t.status === "malformed");

  async function enroll(e) {
    e.preventDefault();
    if (!list.length) { setEnrollError({ issues: [{ code: "required", message: "Enter at least one email.", field: "candidate_email" }] }); return; }
    setPending(true); setEnrollError(null);
    try {
      const before = new Set(active.map(x => x.candidate_id));
      const next = await api.enroll(params.id, list);
      roster.replace(next);
      setEmails(flawed.map(t => t.text).join("\n"));
      const added = next.entries.filter(x => x.active && !before.has(x.candidate_id)).length;
      setNotice(`${added} ${added === 1 ? "candidate" : "candidates"} enrolled${list.length - added ? `; ${list.length - added} already on the roster` : ""}.`
        + (flawed.length ? ` ${flawed.length} ${flawed.length === 1 ? "entry is" : "entries are"} left in the box to correct.` : ""));
    } catch (err) { setEnrollError(err.issues?.length ? err : { message: err.message, issues: [] }); }
    finally { setPending(false); }
  }
  async function toggle(entry) {
    setNotice(null);
    try {
      roster.replace(await api.setEnrollment(params.id, entry.candidate_id, !entry.active));
      setNotice(`${entry.display_name} ${entry.active ? "withdrawn. Their record is kept." : "restored to the roster."}`);
    } catch (err) { setNotice(err.message); }
  }

  return <main className="shell au-page">
    <PageHead crumb={<><a href={paths.exams} onClick={e => { e.preventDefault(); navigate(paths.exams); }}>Exam register</a> <span aria-hidden="true">/</span> <a href={paths.edit(params.id)} onClick={e => { e.preventDefault(); navigate(paths.edit(params.id)); }}>{exam.data.title}</a> <span aria-hidden="true">/</span> Roster</>}
      title="Roster"
      details={<><b>{exam.data.title}</b><i /><StateBadge state={roster.data.state} /><i />{formatWindow(exam.data.opens_at, exam.data.closes_at)}<ModeLabel mode={api.mode} /></>} />

    {closed && <Banner tone="frozen" title="The window has closed">This roster is now a record of who was eligible. It can no longer change.</Banner>}
    {roster.data.state === "draft" && <Banner tone="info" title="Draft exam">Enrolled candidates see nothing until you publish. Their access will then follow the window.</Banner>}

    <div className="workgrid">
      <section className="board" aria-labelledby="roster-title">
        <div className="split"><h2 id="roster-title">Candidates</h2>
          <input type="search" className="search" placeholder="Find name or email" aria-label="Find name or email" value={query} onChange={e => setQuery(e.target.value)} /></div>
        <div className="summary-grid au-summary-4">
          <Stat label="Enrolled" value={two(active.length)} />
          <Stat label="Can enter now" value={two(active.filter(e => e.can_start).length)} />
          <Stat label="Withdrawn" value={two(entries.length - active.length)} />
          <Stat label="Blocked" value={two(entries.filter(e => BLOCKED.has(e.access)).length)} tone={entries.some(e => BLOCKED.has(e.access)) ? "warn" : undefined} />
        </div>
        {notice && <p className="au-notice" role="status">{notice}</p>}
        {entries.length === 0 && <EmptyState art={<TrayArt />} title="No candidates enrolled">Add candidate emails or import a roster CSV. Only enabled accounts with the candidate role can be enrolled.</EmptyState>}
        {entries.length > 0 && shown.length === 0 && <p className="au-none" role="status">No candidates match “{query}”.</p>}
        {shown.length > 0 && <table className="data-table au-stack">
          <caption className="sr-only">Roster for {exam.data.title}</caption>
          <thead><tr><th scope="col">Candidate</th><th scope="col">Entry status</th><th scope="col">Enrollment</th>{!closed && <th scope="col"><span className="sr-only">Action</span></th>}</tr></thead>
          <tbody>{shown.map(e => <tr key={e.candidate_id} className={e.active ? "" : "au-row--muted"}>
            <td data-label="Candidate">{e.display_name}<span className="au-sub">{e.email}</span></td>
            <td data-label="Entry status"><AccessBadge access={e.access} /></td>
            <td data-label="Enrollment">{e.active ? "Active" : "Withdrawn"}</td>
            {!closed && <td data-label="Action"><button className="quiet" onClick={() => toggle(e)}>{e.active ? "Withdraw" : "Restore"}<span className="sr-only"> {e.display_name}</span></button></td>}
          </tr>)}</tbody>
        </table>}
      </section>

      {!closed && <aside className="side" aria-labelledby="add-title">
        <div className="side-head"><h2 id="add-title">Add candidates</h2>
          <div className="au-tabs" role="group" aria-label="How to add candidates">
            <button type="button" className="au-chip" aria-pressed={mode === "type"} onClick={() => setMode("type")}>Type emails</button>
            <button type="button" className="au-chip" aria-pressed={mode === "csv"} onClick={() => setMode("csv")}>Import CSV</button>
          </div></div>
        <div className="side-content">
          {mode === "type" ? <form onSubmit={enroll} noValidate>
            <ErrorSummary error={enrollError} title="These entries could not be enrolled" describe={i => <>{i.row ? <b>{list[i.row - 1] ?? `Entry ${i.row}`} · </b> : null}{i.message}</>} />
            <Field label="Candidate emails" hint="One per line, or separated by commas. Anything that is not an email stays here to fix. If an address has no enabled candidate account, nothing is enrolled.">
              <textarea rows={5} value={emails} onChange={e => setEmails(e.target.value)} placeholder="nora.khan@example.test" /></Field>
            {tokens.length > 0 && <ul className="au-mailchips" aria-label="Emails read from your entry">
              {tokens.map((t, i) => <li key={i} className={`au-mail-chip au-mail-chip--${t.status === "ok" ? "ok" : t.status === "malformed" ? "bad" : "repeat"}`}>
                <span aria-hidden="true">{t.status === "ok" ? "✉" : t.status === "malformed" ? "✕" : "↺"}</span>{t.text}
                {t.status !== "ok" && <em>{t.status === "malformed" ? "check format" : "repeated"}</em>}</li>)}
            </ul>}
            {flawed.length > 0 && <p className="au-sub au-warn" role="status">{flawed.length} {flawed.length === 1 ? "entry does" : "entries do"} not look like an email and will stay in the box for you to fix.</p>}
            <button className="primary block" disabled={pending || (tokens.length > 0 && list.length === 0)}>
              {pending ? "Enrolling…" : flawed.length && list.length ? `Enroll ${list.length} valid ${list.length === 1 ? "email" : "emails"}` : list.length > 1 ? `Enroll ${list.length} candidates` : "Enroll"}</button>
          </form>
            : <ImportPanel template="roster" noun="candidate" validate={text => api.importRoster(params.id, text, { dryRun: true })}
              commit={text => api.importRoster(params.id, text)} onImported={() => { roster.reload(); setNotice(null); }} />}
        </div>
      </aside>}
    </div>
  </main>;
}
