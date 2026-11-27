import React, { useMemo, useState } from "react";
import { ImportPanel } from "./ImportPanel.jsx";
import { Banner } from "./primitives.jsx";

/**
 * SR04 / AT10: administrators import candidate accounts from UTF-8 CSV.
 * Exported for the foundation's /admin/accounts page ("Admin import action
 * uses the foundation identity service", docs/pages.md).
 *
 * The committing response carries each new account's initial password. The
 * SRS requires it to be exposed once, so the sheet below keeps the passwords
 * only in component memory, masks them until revealed, offers a download and
 * a copy, and forgets them when the administrator confirms they are saved.
 */
export function CandidateImportPanel({ api, onImported }) {
  const [issued, setIssued] = useState(null);
  return <div className="au-accounts-import">
    <ImportPanel template="candidates" noun="candidate account"
      validate={text => api.importCandidates(text, { dryRun: true })}
      commit={text => api.importCandidates(text)}
      onImported={result => { setIssued(result.credentials?.length ? result.credentials : null); onImported?.(result); }} />
    {issued && <CredentialSheet credentials={issued} onDone={() => setIssued(null)} />}
  </div>;
}

function CredentialSheet({ credentials, onDone }) {
  const [revealed, setRevealed] = useState(false);
  const [copied, setCopied] = useState(false);
  const csvHref = useMemo(() => "data:text/csv;charset=utf-8," + encodeURIComponent(
    "email,initial_password\n" + credentials.map(c => `${c.email},${c.initial_password}`).join("\n") + "\n"), [credentials]);
  async function copyAll() {
    try {
      await navigator.clipboard.writeText(credentials.map(c => `${c.email}\t${c.initial_password}`).join("\n"));
      setCopied(true);
    } catch { setCopied(false); }
  }
  return <section className="au-credsheet" aria-labelledby="credsheet-title">
    <Banner tone="warn" title="Initial passwords · shown once">
      These passwords are not kept in readable form and cannot be shown again. Download or copy them now and hand each one to its candidate privately.
    </Banner>
    <div className="split au-credsheet__head">
      <h3 id="credsheet-title" className="au-subhead">{credentials.length} new {credentials.length === 1 ? "account" : "accounts"}</h3>
      <label className="au-check"><input type="checkbox" checked={revealed} onChange={e => setRevealed(e.target.checked)} /> Show passwords</label>
    </div>
    <table className="data-table au-stack">
      <caption className="sr-only">New candidate accounts and their one-time initial passwords</caption>
      <thead><tr><th scope="col">Email</th><th scope="col">Initial password</th></tr></thead>
      <tbody>{credentials.map(c => <tr key={c.email}>
        <td data-label="Email">{c.email}</td>
        <td data-label="Initial password" className="au-mono">{revealed ? c.initial_password : "•".repeat(12)}<span className="sr-only">{revealed ? "" : " (hidden; tick Show passwords to read it)"}</span></td>
      </tr>)}</tbody>
    </table>
    <div className="row au-credsheet__actions">
      <a className="secondary au-credsheet__download" href={csvHref} download="initial-passwords.csv">Download CSV</a>
      <button type="button" className="secondary" onClick={copyAll}>{copied ? "Copied ✓" : "Copy all"}</button>
      <button type="button" className="primary" onClick={onDone}>I have saved them · close</button>
    </div>
  </section>;
}
