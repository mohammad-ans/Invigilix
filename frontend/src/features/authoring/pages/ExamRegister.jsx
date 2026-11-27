import React, { useMemo, useState } from "react";
import { PageHead } from "../../../design/Folio.jsx";
import { paths } from "../paths.js";
import { useResource } from "../hooks.js";
import { formatDuration, formatMarks, formatWindow, two, STATE } from "../domain/format.js";
import { Dialog } from "../components/instruments.jsx";
import { ExamForm, blankDetails } from "../components/ExamForm.jsx";
import { LedgerArt } from "../components/illustrations.jsx";
import { EmptyState, Loading, LoadError, ModeLabel, StateBadge, Stat } from "../components/primitives.jsx";

const FILTERS = ["all", "draft", "scheduled", "ongoing", "completed"];

/** /examiner/exams — the examiner's register of owned exams (FR03). */
export default function ExamRegister({ api, navigate }) {
  const exams = useResource(() => api.listExams(), [api]);
  const [filter, setFilter] = useState("all");
  const [creating, setCreating] = useState(false);
  const counts = useMemo(() => Object.fromEntries(FILTERS.map(f => [f, (exams.data ?? []).filter(e => f === "all" || e.state === f).length])), [exams.data]);
  const shown = (exams.data ?? []).filter(e => filter === "all" || e.state === filter);

  async function create(details) {
    const exam = await api.createExam(details);
    navigate(paths.edit(exam.id));
  }

  return <main className="shell au-page">
    <PageHead crumb="Examiner workspace" title="Exam register"
      details={<><b>Owned exams</b><i />{exams.data ? `${counts.all} on record` : "Loading"}<ModeLabel mode={api.mode} /></>}
      aside={<button className="primary au-cta" onClick={() => setCreating(true)}><span aria-hidden="true">＋</span> New draft</button>} />

    {exams.error && <LoadError error={exams.error} retry={exams.reload} />}
    {exams.loading && !exams.data && <Loading label="Opening the register" />}

    {exams.data && <section className="board au-register">
      <div className="summary-grid au-summary-4">
        {FILTERS.slice(1).map(s => <Stat key={s} label={STATE[s].label} value={two(counts[s])} />)}
      </div>

      <div className="au-filters" role="group" aria-label="Show exams by state">
        {FILTERS.map(f => <button key={f} type="button" className="au-chip" aria-pressed={filter === f} onClick={() => setFilter(f)}>
          {f === "all" ? "All" : STATE[f].label}<span className="au-chip__count">{counts[f]}</span></button>)}
      </div>

      {counts.all === 0 && <EmptyState art={<LedgerArt />} title="No exams on record yet"
        action={<button className="primary" onClick={() => setCreating(true)}>Start a draft</button>}>
        A draft holds the title, window, duration and declared total. Add questions from your bank, then publish.
      </EmptyState>}
      {counts.all > 0 && shown.length === 0 && <p className="au-none" role="status">No {STATE[filter].label.toLowerCase()} exams.</p>}

      {shown.length > 0 && <table className="data-table au-ledger-table au-stack">
        <caption className="sr-only">Exams you own, newest window first</caption>
        <thead><tr><th scope="col">No.</th><th scope="col">Exam</th><th scope="col">Window</th><th scope="col">Paper</th><th scope="col">Roster</th><th scope="col">State</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{shown.map((e, n) => {
          const balanced = Number(e.allocated_marks) === Number(e.total_marks) && e.item_count > 0;
          return <tr key={e.id}>
            <td data-label="No." className="au-entry-no">{two(n + 1)}</td>
            <td data-label="Exam"><a className="au-exam-title" href={paths.edit(e.id)} onClick={ev => { ev.preventDefault(); navigate(paths.edit(e.id)); }}>{e.title}</a>
              <span className="au-sub">{formatDuration(e.duration_minutes)} per attempt{e.shuffle_questions ? " · shuffled" : ""}</span></td>
            <td data-label="Window" className="au-mono">{formatWindow(e.opens_at, e.closes_at)}</td>
            <td data-label="Paper"><span className="au-mono">{e.item_count} {e.item_count === 1 ? "item" : "items"}</span>
              <span className={`au-sub ${balanced ? "" : "au-warn"}`}>{balanced ? "" : <span aria-hidden="true">! </span>}{formatMarks(e.allocated_marks)} / {formatMarks(e.total_marks)} marks{balanced ? "" : <span className="sr-only"> (does not match)</span>}</span></td>
            <td data-label="Roster" className="au-mono">{e.enrolled}</td>
            <td data-label="State"><StateBadge state={e.state} /></td>
            <td data-label="Actions" className="au-row-actions">
              <button className="quiet" onClick={() => navigate(paths.edit(e.id))}>{e.state === "draft" ? "Edit" : "Review"}<span className="sr-only"> {e.title}</span></button>
              <button className="quiet" onClick={() => navigate(paths.enrollment(e.id))}>Roster<span className="sr-only"> for {e.title}</span></button>
              <button className="quiet" onClick={() => navigate(paths.preview(e.id))}>Preview<span className="sr-only"> {e.title}</span></button>
            </td>
          </tr>;
        })}</tbody>
      </table>}
    </section>}

    {creating && <Dialog title="New exam draft" onClose={() => setCreating(false)} wide>
      <p className="au-dialog__lead">Set the particulars now. You can change any of them until you publish.</p>
      <ExamForm initial={blankDetails()} submitLabel="Create draft" onSubmit={create} onCancel={() => setCreating(false)} />
    </Dialog>}
  </main>;
}
