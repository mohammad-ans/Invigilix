import React, { useState } from "react";
import { useResource } from "../hooks.js";
import { DIFFICULTIES, KINDS } from "../domain/rules.js";
import { KIND, shortId } from "../domain/format.js";
import { Dialog } from "./instruments.jsx";
import { DifficultyScale, EmptyState, KindTag, Loading, LoadError, VersionTag } from "./primitives.jsx";

export const emptyFilters = { q: "", topic: "", difficulty: "", kind: "" };

/** Search, topic, difficulty and type filters shared by the bank and the picker. */
export function BankFilters({ filters, onChange, topics }) {
  const set = (k, v) => onChange({ ...filters, [k]: v });
  const active = Object.values(filters).some(Boolean);
  return <div className="au-bank-filters" role="search">
    <label className="au-bank-filters__search"><span className="sr-only">Search prompts and topics</span>
      <input type="search" className="search" placeholder="Search prompts and topics" value={filters.q} onChange={e => set("q", e.target.value)} /></label>
    <label><span className="au-field__label">Topic</span>
      <select className="small-select" value={filters.topic} onChange={e => set("topic", e.target.value)}>
        <option value="">All topics</option>{topics.map(t => <option key={t}>{t}</option>)}</select></label>
    <label><span className="au-field__label">Difficulty</span>
      <select className="small-select" value={filters.difficulty} onChange={e => set("difficulty", e.target.value)}>
        <option value="">Any</option>{DIFFICULTIES.map(d => <option key={d} value={d}>{d[0].toUpperCase() + d.slice(1)}</option>)}</select></label>
    <label><span className="au-field__label">Type</span>
      <select className="small-select" value={filters.kind} onChange={e => set("kind", e.target.value)}>
        <option value="">Any</option>{KINDS.map(k => <option key={k} value={k}>{KIND[k].label}</option>)}</select></label>
    {active && <button type="button" className="quiet" onClick={() => onChange(emptyFilters)}>Clear filters</button>}
  </div>;
}

/** Dialog for adding bank questions to a draft paper. */
export function BankPicker({ api, onClose, onPick, exclude }) {
  const [filters, setFilters] = useState(emptyFilters);
  const all = useResource(() => api.searchQuestions(), [api]);
  const found = useResource(() => api.searchQuestions(filters), [api, filters.q, filters.topic, filters.difficulty, filters.kind]);
  const [added, setAdded] = useState([]);
  const topics = [...new Set((all.data ?? []).map(q => q.latest.topic))].sort();
  return <Dialog title="Add questions from your bank" onClose={onClose} wide>
    <p className="au-dialog__lead">Each added slot pins the version shown. Later bank edits will not change it.</p>
    <BankFilters filters={filters} onChange={setFilters} topics={topics} />
    {found.error && <LoadError error={found.error} retry={found.reload} />}
    {found.loading && !found.data && <Loading label="Searching the bank" />}
    {found.data && found.data.length === 0 && <EmptyState title="No questions match">Clear a filter or add questions in the bank.</EmptyState>}
    {found.data && found.data.length > 0 && <ul className="au-pick">{found.data.map(q => {
      const taken = exclude.has(q.id) || added.includes(q.id);
      return <li key={q.id}>
        <div><p className="au-pick__prompt">{q.latest.prompt}</p>
          <div className="au-slot__meta"><span className="au-mono au-sub">{shortId(q.id)}</span><KindTag kind={q.latest.kind} /><span>{q.latest.topic}</span><DifficultyScale level={q.latest.difficulty} /><VersionTag number={q.latest.number} /></div></div>
        <button type="button" className={taken ? "quiet" : "secondary"} disabled={taken}
          onClick={() => { onPick(q); setAdded(a => [...a, q.id]); }}>{taken ? "On paper ✓" : "Add"}<span className="sr-only"> {q.latest.prompt}</span></button>
      </li>;
    })}</ul>}
    <div className="actions"><span className="au-sub" role="status">{added.length ? `${added.length} added. Save the paper to keep them.` : ""}</span><button className="primary" onClick={onClose}>Done</button></div>
  </Dialog>;
}
