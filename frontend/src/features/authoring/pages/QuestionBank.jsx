import React, { useRef, useState } from "react";
import { PageHead } from "../../../design/Folio.jsx";
import { paths } from "../paths.js";
import { useResource } from "../hooks.js";
import { RULE, letter, shortId, two } from "../domain/format.js";
import { Dialog } from "../components/instruments.jsx";
import { ImportPanel } from "../components/ImportPanel.jsx";
import { QuestionForm, blankQuestion } from "../components/QuestionForm.jsx";
import { BankFilters, emptyFilters } from "../components/BankPicker.jsx";
import { VersionDiff } from "../components/VersionDiff.jsx";
import {
  Banner, DifficultyScale, EmptyState, KindTag, Loading, LoadError, ModeLabel, VersionTag,
} from "../components/primitives.jsx";

/** /examiner/questions — filterable bank with version history (FR04, SR04). */
export default function QuestionBank({ api, navigate }) {
  const [filters, setFilters] = useState(emptyFilters);
  const all = useResource(() => api.searchQuestions(), [api]);
  const found = useResource(() => api.searchQuestions(filters), [api, filters.q, filters.topic, filters.difficulty, filters.kind]);
  const [selected, setSelected] = useState(null);
  const [dialog, setDialog] = useState(null); // "new" | "revise" | "import"
  const [notice, setNotice] = useState(null);
  const detailRef = useRef(null);
  const detail = useResource(() => (selected ? api.getQuestion(selected) : Promise.resolve(null)), [api, selected]);
  const topics = [...new Set((all.data ?? []).map(q => q.latest.topic))].sort();

  function refresh() { all.reload(); found.reload(); detail.reload(); }
  function open(id) {
    setSelected(id); setNotice(null);
    requestAnimationFrame(() => { if (window.matchMedia("(max-width: 820px)").matches) detailRef.current?.scrollIntoView({ behavior: "smooth" }); detailRef.current?.focus({ preventScroll: true }); });
  }

  async function create(body) {
    const q = await api.createQuestion(body);
    setDialog(null); refresh(); setSelected(q.id);
    setNotice({ tone: "ok", text: `Question ${shortId(q.id)} added as version 1.` });
  }
  async function revise(body) {
    const result = await api.reviseQuestion(selected, body);
    setDialog(null); refresh();
    setNotice(result.created
      ? { tone: "ok", text: `Saved as version ${result.question.version_count}. Papers that pinned earlier versions keep them.` }
      : { tone: "info", text: `No changes: this matches version ${result.question.version_count}, so no new version was created.` });
  }

  const current = detail.data?.versions?.[0];
  return <main className="shell au-page">
    <PageHead crumb="Examiner workspace" title="Question bank"
      details={<><b>{all.data ? `${all.data.length} questions` : "Loading"}</b><i />{topics.length} topics<i />Every edit appends a version<ModeLabel mode={api.mode} /></>}
      aside={<div className="row au-head-actions">
        <button className="secondary" onClick={() => setDialog("import")}>Import CSV</button>
        <button className="primary au-cta" onClick={() => setDialog("new")}><span aria-hidden="true">＋</span> New question</button></div>} />

    <div className="workgrid au-bank">
      <section className="board" aria-labelledby="bank-results">
        <h2 id="bank-results" className="sr-only">Questions</h2>
        <BankFilters filters={filters} onChange={setFilters} topics={topics} />
        {found.error && <LoadError error={found.error} retry={found.reload} />}
        {found.loading && !found.data && <Loading label="Searching the bank" />}
        {found.data && <p className="au-sub au-count" role="status">{found.data.length} {found.data.length === 1 ? "question" : "questions"}{Object.values(filters).some(Boolean) ? " match" : ""}</p>}
        {all.data?.length === 0 && <EmptyState title="The bank is empty" action={<button className="primary" onClick={() => setDialog("new")}>Write the first question</button>}>
          Write questions one at a time or import a CSV. Each keeps its full version history.</EmptyState>}
        {found.data?.length === 0 && all.data?.length > 0 && <EmptyState title="No questions match these filters" action={<button className="secondary" onClick={() => setFilters(emptyFilters)}>Clear filters</button>} />}
        {found.data?.length > 0 && <table className="data-table au-bank-table au-stack">
          <caption className="sr-only">Bank questions, latest version shown</caption>
          <thead><tr><th scope="col">ID</th><th scope="col">Question</th><th scope="col">Type</th><th scope="col">Difficulty</th><th scope="col">Version</th></tr></thead>
          <tbody>{found.data.map(q => <tr key={q.id} className={selected === q.id ? "au-row--selected" : ""} aria-current={selected === q.id ? "true" : undefined}>
            <td data-label="ID"><span className="au-mono au-id">{shortId(q.id)}</span></td>
            <td data-label="Question"><button type="button" className="au-row-link" onClick={() => open(q.id)}>{q.latest.prompt}</button><span className="au-sub">{q.latest.topic}</span></td>
            <td data-label="Type"><KindTag kind={q.latest.kind} /></td>
            <td data-label="Difficulty"><DifficultyScale level={q.latest.difficulty} /></td>
            <td data-label="Version"><VersionTag number={q.latest.number} /></td>
          </tr>)}</tbody>
        </table>}
      </section>

      <aside className="side au-detail" ref={detailRef} tabIndex={-1} aria-labelledby="detail-title">
        <div className="side-head"><h2 id="detail-title">{current ? `Question ${shortId(selected)}` : "Question record"}</h2>
          {current && <p className="au-sub">{detail.data.versions.length} {detail.data.versions.length === 1 ? "version" : "versions"} · current v{current.number}</p>}</div>
        <div className="side-content">
          {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}
          {!selected && <p className="au-sub">Choose a question to read its key, rubric, version history and the papers that use it.</p>}
          {selected && detail.loading && !detail.data && <Loading />}
          {detail.error && <LoadError error={detail.error} retry={detail.reload} />}
          {current && <>
            <div className="au-slot__meta"><KindTag kind={current.kind} /><span>{current.topic}</span><DifficultyScale level={current.difficulty} /></div>
            <p className="au-detail__prompt">{current.prompt}</p>
            {current.options.length > 0 && <ol className="au-keylist">{current.options.map((o, n) => <li key={o.id} className={o.correct ? "au-is-key" : ""}>
              <span className="opt-letter">{letter(n)}</span>{o.label}{o.correct && <span className="au-keymark"><span aria-hidden="true">✓</span> Key</span>}</li>)}</ol>}
            <p className="au-sub">Marking: {RULE[current.marking_rule]}</p>
            {current.rubric && <div className="au-rubric"><span className="mini">Rubric · private</span><p>{current.rubric}</p></div>}
            <button className="secondary block" onClick={() => setDialog("revise")}>Revise (creates v{current.number + 1})</button>

            <h3 className="au-subhead">Used on papers</h3>
            {detail.data.usage.length === 0 ? <p className="au-sub">Not on any paper yet.</p>
              : <ul className="au-usage">{detail.data.usage.map(u => <li key={u.exam_id + u.slot}>
                <a href={paths.edit(u.exam_id)} onClick={e => { e.preventDefault(); navigate(paths.edit(u.exam_id)); }}>{u.exam_title}</a>
                <span className="au-sub"> · slot {two(u.slot)} · v{u.version_number}{u.frozen ? " · frozen" : " · draft"}</span></li>)}</ul>}

            <h3 className="au-subhead">Version history</h3>
            <ol className="au-history">{detail.data.versions.map((v, n) => <li key={v.id} className={n === 0 ? "current" : ""}>
              <span className="au-history__tag">v{v.number}{n === 0 ? " · current" : ""}</span>
              <p>{v.prompt}</p>
              {v.options.length > 0 && <p className="au-sub">Key: {v.options.map((o, i) => o.correct ? letter(i) : null).filter(Boolean).join(", ")} · {v.options.length} options</p>}
              {detail.data.versions[n + 1] && <details className="au-diff-toggle" open={n === 0}>
                <summary>Changes from v{detail.data.versions[n + 1].number}</summary>
                <VersionDiff prev={detail.data.versions[n + 1]} next={v} />
              </details>}
            </li>)}</ol>
          </>}
        </div>
      </aside>
    </div>

    {dialog === "new" && <Dialog title="New question" onClose={() => setDialog(null)} wide>
      <QuestionForm initial={blankQuestion()} submitLabel="Add to bank" onSubmit={create} onCancel={() => setDialog(null)} />
    </Dialog>}
    {dialog === "revise" && current && <Dialog title={`Revise question ${shortId(selected)}`} onClose={() => setDialog(null)} wide>
      <QuestionForm initial={current} submitLabel={`Save as v${current.number + 1}`} onSubmit={revise} onCancel={() => setDialog(null)}
        note={`Saving appends version ${current.number + 1}. ${detail.data.usage.length ? "Papers that use this question keep the version they pinned." : ""}`} />
    </Dialog>}
    {dialog === "import" && <Dialog title="Import questions" onClose={() => setDialog(null)} wide>
      <p className="au-dialog__lead">Known question IDs append a version when content differs; identical rows are left unchanged. An invalid row imports nothing.</p>
      <ImportPanel template="questions" noun="question" validate={text => api.importQuestions(text, { dryRun: true })} commit={text => api.importQuestions(text)} onImported={refresh} />
    </Dialog>}
  </main>;
}
