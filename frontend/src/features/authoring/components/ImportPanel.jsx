import React, { useMemo, useState } from "react";
import { TEMPLATES, parseCsv } from "../domain/csv.js";
import { Banner } from "./primitives.jsx";

const decoder = new TextDecoder("utf-8", { fatal: true });

/**
 * Two-step CSV import (SR04): check the file (server dry run), read the
 * proofing report, then import. The commit is atomic on the server, so an
 * invalid file never changes records.
 */
export function ImportPanel({ template, noun, validate, commit, onImported }) {
  const [file, setFile] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState("");
  const [done, setDone] = useState(null);
  const tpl = TEMPLATES[template];
  const templateHref = useMemo(() => "data:text/csv;charset=utf-8," + encodeURIComponent(tpl.text), [tpl]);

  async function choose(f) {
    setReport(null); setError(null); setDone(null);
    if (!f) { setFile(null); return; }
    try {
      const text = decoder.decode(await f.arrayBuffer());
      const rows = parseCsv(text).rows.length;
      setFile({ name: f.name, size: f.size, text, rows });
    } catch {
      setFile(null);
      setError({ message: "This file is not UTF-8 text. Export it from your spreadsheet as “CSV UTF-8” and choose it again." });
    }
  }

  async function run(step) {
    setBusy(step); setError(null);
    try {
      if (step === "check") setReport(await validate(file.text));
      else {
        const result = await commit(file.text);
        setDone(result); setReport(null); setFile(null); onImported?.(result);
      }
    } catch (e) {
      if (e.issues?.length) setReport({ rows: file.rows, created: 0, updated: 0, unchanged: 0, issues: e.issues, committed: false, headerProblem: e.code === "import_invalid" && e.issues.some(i => i.row === 1 || !i.row) });
      else setError(e);
    } finally { setBusy(""); }
  }

  const clean = report && report.issues.length === 0;
  return <div className="au-import">
    <label className={`au-drop${file ? " au-drop--loaded" : ""}`}
      onDragOver={e => { e.preventDefault(); e.currentTarget.classList.add("au-drop--over"); }}
      onDragLeave={e => e.currentTarget.classList.remove("au-drop--over")}
      onDrop={e => { e.preventDefault(); e.currentTarget.classList.remove("au-drop--over"); choose(e.dataTransfer.files[0]); }}>
      <input type="file" accept=".csv,text/csv" className="sr-only" onChange={e => choose(e.target.files[0])} />
      <span className="au-drop__tray" aria-hidden="true"><i /><i /></span>
      {file
        ? <span><strong>{file.name}</strong><span className="au-drop__meta">{file.rows} data rows · {(file.size / 1024).toFixed(1)} KB · choose another file</span></span>
        : <span><strong>Choose a UTF-8 CSV file</strong><span className="au-drop__meta">or drop it here · one {noun} per row</span></span>}
    </label>
    <p className="au-import__help">Start from the <a href={templateHref} download={tpl.filename}>CSV template</a>. The header row must match it exactly.</p>

    {error && <Banner tone="error" title="The file could not be checked">{error.message}</Banner>}
    {done && <Banner tone="ok" title="Import complete">
      {done.created} created · {done.updated} updated · {done.unchanged} already present. Rerunning the same file changes nothing.
    </Banner>}

    {report && <section className="au-proof" aria-live="polite" aria-labelledby="proof-title">
      <h3 id="proof-title" className="au-subhead">{clean ? "File checked · ready to import" : "Proofing report · nothing was imported"}</h3>
      {!report.headerProblem && <dl className="au-proof__counts">
        <div><dt>Rows</dt><dd>{report.rows}</dd></div>
        <div><dt>New</dt><dd>{report.created}</dd></div>
        <div><dt>Updated</dt><dd>{report.updated}</dd></div>
        <div><dt>Unchanged</dt><dd>{report.unchanged}</dd></div>
        <div className={report.issues.length ? "bad" : ""}><dt>Errors</dt><dd>{report.issues.length}</dd></div>
      </dl>}
      {report.issues.length > 0 && <table className="data-table au-proof__table">
        <caption className="sr-only">Rows that need correction</caption>
        <thead><tr><th scope="col">Row</th><th scope="col">Field</th><th scope="col">Correction</th></tr></thead>
        <tbody>{report.issues.map((i, n) => <tr key={n}>
          <td data-label="Row" className="au-mono">{i.row ?? "—"}</td>
          <td data-label="Field"><code>{i.field ?? "file"}</code></td>
          <td data-label="Correction">{i.message}</td></tr>)}</tbody>
      </table>}
    </section>}

    <div className="row au-import__actions">
      <button type="button" className="secondary" disabled={!file || !!busy} onClick={() => run("check")}>{busy === "check" ? "Checking…" : "Check file"}</button>
      <button type="button" className="primary" disabled={!file || !clean || !!busy} onClick={() => run("commit")}>
        {busy === "commit" ? "Importing…" : clean ? `Import ${report.rows} ${report.rows === 1 ? "row" : "rows"}` : "Import"}
      </button>
    </div>
  </div>;
}
