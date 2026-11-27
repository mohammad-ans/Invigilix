import React, { useEffect, useState } from "react";
import { ImportPanel } from "../features/authoring/components/ImportPanel.jsx";
import { api } from "./api.js";

const roles = ["admin", "examiner", "candidate"];

function AccountForm({ record, onDone, onCancel }) {
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = { display_name: form.get("display_name"), roles: form.getAll("role"), enabled: form.has("enabled") };
    if (!body.roles.length) { setError("Choose at least one role."); return; }
    if (!record) Object.assign(body, { email: form.get("email"), password: form.get("password") });
    setSaving(true); setError("");
    try {
      await api("/admin/accounts" + (record ? "/" + record.id : ""), record ? "PATCH" : "POST", body);
      onDone();
    } catch (e) { setError(e.issues?.map(i => i.message).join(" ") || e.message); setSaving(false); }
  }
  return <form className="office-form sheet" onSubmit={submit}>
    <h2>{record ? "Edit access" : "Create account"}</h2>
    <label>Display name<input name="display_name" required autoFocus maxLength={150} defaultValue={record?.display_name} /></label>
    {record ? <p>{record.email}</p> : <>
      <label>Email address<input name="email" type="email" autoComplete="off" required maxLength={254} /></label>
      <label>Initial password<input name="password" type="password" autoComplete="new-password" required minLength={12} maxLength={256} /></label>
      <small>Use at least 12 characters.</small>
    </>}
    <fieldset><legend>Assigned roles</legend>{roles.map(role => <label className="office-check" key={role}><input type="checkbox" name="role" value={role} defaultChecked={record ? record.roles.includes(role) : role === "candidate"} />{role}</label>)}</fieldset>
    <label className="office-check"><input type="checkbox" name="enabled" defaultChecked={record?.enabled ?? true} />Access enabled</label>
    {error && <p role="alert">{error}</p>}
    <div className="row"><button disabled={saving} className="primary">{saving ? "Saving…" : record ? "Save access" : "Create account"}</button><button type="button" className="secondary" onClick={onCancel}>Cancel</button></div>
  </form>;
}

export function Accounts() {
  const [rows, setRows] = useState(null), [query, setQuery] = useState("");
  const [editor, setEditor] = useState(undefined), [revision, setRevision] = useState(0);
  const [error, setError] = useState(""), [credentials, setCredentials] = useState([]);
  useEffect(() => {
    let active = true;
    api("/admin/accounts").then(data => active && setRows(data)).catch(e => active && setError(e.message));
    return () => { active = false; };
  }, [revision]);
  const refresh = () => { setEditor(undefined); setError(""); setRevision(n => n + 1); };
  const shown = rows?.filter(r => (r.display_name + " " + r.email + " " + r.roles.join(" ")).toLowerCase().includes(query.trim().toLowerCase()));
  return <main className="shell office-register"><header className="pagehead"><div><p className="eyebrow">Administration</p><h1>Account register</h1></div>
    <button className="primary" onClick={() => setEditor(null)}>New account</button></header>
    {editor !== undefined && <AccountForm key={editor?.id || "new"} record={editor} onDone={refresh} onCancel={() => setEditor(undefined)} />}
    <section className="sheet office-form"><label>Find an account<input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Name, email or role" /></label>
      {error && <p role="alert">{error} <button className="secondary" onClick={refresh}>Retry</button></p>}
      {!rows ? <p role="status">Loading accounts…</p> : <><p>{shown.length} {shown.length === 1 ? "account" : "accounts"}</p>
        <ul className="office-list">{shown.map(row => <li key={row.id}><div><strong>{row.display_name}</strong><small>{row.email}</small></div>
          <span>{row.roles.join(", ")} · {row.enabled ? "Enabled" : "Disabled"}</span>
          <button className="secondary" aria-label={"Edit access for " + row.display_name} onClick={() => setEditor(row)}>Edit access</button></li>)}</ul></>}
    </section>
    <details className="sheet office-import"><summary>Import candidate accounts from CSV</summary>
      <ImportPanel template="candidates" noun="candidate" validate={csv => api("/admin/accounts/import?dry_run=true", "POST", csv, true)}
        commit={csv => api("/admin/accounts/import", "POST", csv, true)} onImported={r => { setCredentials(r.credentials); refresh(); }} />
      {!!credentials.length && <section><h3>Initial passwords</h3><p>Give each candidate their own password before closing this page.</p>
        <dl>{credentials.map(c => <React.Fragment key={c.email}><dt>{c.email}</dt><dd><code>{c.initial_password}</code></dd></React.Fragment>)}</dl>
        <button className="secondary" onClick={() => setCredentials([])}>Dismiss passwords</button></section>}
    </details>
  </main>;
}
