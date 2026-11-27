import React, { useEffect, useState } from "react";
import { authoringRoutes, matchRoute as matchAuthoring, HttpAuthoringApi } from "../features/authoring/index.js";
import { resultsRoutes, matchRoute as matchResults, HttpResultsApi, VerifyPage } from "../features/results/index.js";
import { CandidateAttempt, CandidateExams, purgeDeliveryAccount } from "../features/delivery/pages.jsx";
import { Accounts } from "./Accounts.jsx";
import { api } from "./api.js";
import "./office.css";

const authoring = new HttpAuthoringApi(), results = new HttpResultsApi();
const identityKey = "folio-offline-identity";
const navigate = to => window.location.assign(to);
const links = [
  ["admin", "/admin/accounts", "Accounts"], ["examiner", "/examiner/exams", "Exam register"],
  ["examiner", "/examiner/questions", "Question bank"], ["candidate", "/me/exams", "My exams"],
  ["candidate", "/me/results", "My results"],
];
const path = location.pathname.replace(/\/+$/, "") || "/";
const attemptId = path.match(/^\/attempts\/([\w-]+)$/)?.[1];

function remembered() {
  try { return JSON.parse(localStorage.getItem(identityKey)); } catch { return null; }
}

async function remember(account) {
  const prior = remembered();
  try {
    if (account) localStorage.setItem(identityKey, JSON.stringify({
      id: account.id, expires_at: account.expires_at, candidate: account.roles.includes("candidate"),
    }));
    else localStorage.removeItem(identityKey);
  } catch { /* Live access also works when browser storage is unavailable. */ }
  if (prior?.candidate && (prior.id !== account?.id || !account?.roles.includes("candidate"))) {
    await purgeDeliveryAccount(prior.id);
  }
}

function SignIn({ onSignIn }) {
  const [error, setError] = useState(""), [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true); setError("");
    try {
      const account = await api("/sessions", "POST", { email: form.get("email"), password: form.get("password") });
      await onSignIn(account);
    } catch (e) { setError(e.message); setBusy(false); }
  }
  return <main className="shell office-entry"><section className="office-cover">
    <h1>Sign in</h1>
    <p>Use the account issued by your examination office.</p>
    <form className="office-form" onSubmit={submit}>
      <label>Email address<input type="email" name="email" required autoComplete="username" maxLength={254} /></label>
      <label>Password<input type="password" name="password" required autoComplete="current-password" maxLength={256} /></label>
      {error && <p role="alert">{error}</p>}
      <button className="primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    </form>
  </section><figure className="office-plate"><img src="/transect.png" alt="Illustrated field transect from riverbank to tree line" /><figcaption>Field studies <span>Vegetation transect</span></figcaption></figure></main>;
}

function MyResults() {
  const [rows, setRows] = useState(null), [error, setError] = useState("");
  useEffect(() => { api("/me/results").then(setRows).catch(e => setError(e.message)); }, []);
  return <main className="shell"><header className="pagehead"><div><p className="eyebrow">Candidate</p><h1>My results</h1></div></header>
    <section className="sheet">{error ? <p role="alert">{error}</p> : !rows ? <p>Loading results…</p> : !rows.length ?
      <p>Your results will appear here when your examiner releases them.</p> : <ul className="office-list">{rows.map(row =>
        <li key={row.attempt_id}><div><strong>{row.title}</strong><small>Released {new Date(row.results_published_at).toLocaleString()}</small></div>
          <a className="secondary" href={"/me/attempts/" + row.attempt_id + "/result"}>View result</a></li>)}</ul>}</section></main>;
}

function Workspace({ account }) {
  const home = links.find(([role]) => account.roles.includes(role))?.[1];
  const required = path.startsWith("/examiner/") ? "examiner" : path.startsWith("/admin/") ? "admin" : "candidate";
  const landing = path === "/" || path === "/login";
  useEffect(() => { if (landing && home) location.replace(home); }, [landing, home]);
  if (landing) return <main className="shell">Opening your workspace…</main>;
  if (!account.roles.includes(required)) return <main className="shell"><h1>Access restricted</h1><a href={home}>Open my workspace</a></main>;
  if (path === "/admin/accounts") return <Accounts />;
  if (path === "/me/exams") return <CandidateExams navigate={navigate} />;
  if (path === "/me/results") return <MyResults />;
  if (attemptId) return <CandidateAttempt accountId={account.id} attemptId={attemptId} />;
  const author = matchAuthoring(path), match = author || matchResults(path);
  const route = (author ? authoringRoutes : resultsRoutes).find(r => r.name === match?.name);
  if (!route) return <main className="shell"><h1>Page unavailable</h1><a href={home}>Open my workspace</a></main>;
  const examId = path.startsWith("/examiner/exams/") && match.params.id;
  return <>{examId && <nav className="office-exam-nav" aria-label="Current exam">
    {[["edit", "Paper"], ["enrollment", "Roster"], ["monitor", "Monitor"], ["marking", "Marking"], ["results", "Results"]].map(([slug, label]) =>
      <a key={slug} href={`/examiner/exams/${examId}/${slug}`} aria-current={path.endsWith("/" + slug) ? "page" : undefined}>{label}</a>)}</nav>}
    <route.Page api={author ? authoring : results} params={match.params} navigate={navigate} /></>;
}

export default function App() {
  const [account, setAccount] = useState(null), [loading, setLoading] = useState(true);
  const [error, setError] = useState(""), [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true, generation = 0;
    async function restore() {
      const call = ++generation;
      try {
        const current = await api("/session");
        if (!active || call !== generation) return;
        await remember(current); setAccount(current); setError("");
      } catch (e) {
        if (!active || call !== generation) return;
        const cached = remembered();
        if (e.offline && attemptId && cached?.candidate && Date.parse(cached.expires_at) > Date.now()) {
          setAccount({ id: cached.id, roles: ["candidate"], display_name: "Offline workspace", expires_at: cached.expires_at });
        } else {
          setAccount(null); setError(e.status === 401 ? "" : e.message);
          if (e.status === 401) await remember(null).catch(() => {});
        }
      } finally { if (active && call === generation) setLoading(false); }
    }
    restore();
    const pageshow = e => { if (e.persisted) restore(); };
    const storage = e => { if (e.key === identityKey) { setLoading(true); restore(); } };
    window.addEventListener("storage", storage); window.addEventListener("pageshow", pageshow);
    window.addEventListener("online", restore);
    return () => { active = false; window.removeEventListener("online", restore); window.removeEventListener("storage", storage); window.removeEventListener("pageshow", pageshow); };
  }, []);
  useEffect(() => {
    if (!account?.expires_at) return;
    const timer = setTimeout(() => location.reload(), Math.max(0, Date.parse(account.expires_at) - Date.now()));
    return () => clearTimeout(timer);
  }, [account]);
  async function logout() {
    setBusy(true);
    try {
      await api("/session", "DELETE");
      setAccount(null);
      await remember(null);
      location.replace("/login");
    } catch (e) { setError(e.message); setBusy(false); }
  }
  const roleLinks = links.filter(([role]) => account?.roles.includes(role));
  return <><header className="appbar"><div className="bar-inner office-bar">
    <a href="/" className="brand office-brand" aria-label="Folio home"><span className="brand-mark" aria-hidden="true"><i/><i/><i/></span><b>Folio</b><small>Examination office</small></a>
    <nav aria-label="Office navigation">{roleLinks.map(([,to,label]) => <a key={to} href={to} aria-current={path === to ? "page" : undefined}>{label}</a>)}
      <a href="/verify" aria-current={path === "/verify" ? "page" : undefined}>Verify report</a>
      {account && <button disabled={busy} onClick={logout}>Sign out</button>}{!account && path === "/verify" && <a href="/login">Sign in</a>}</nav>
    </div></header>
    {error && <p className="office-error" role="alert">{error} <button className="secondary" onClick={() => location.reload()}>Retry</button></p>}
    {path === "/verify" ? <VerifyPage api={results} /> : loading ? <main className="shell" role="status">Opening the examination office…</main> :
      account ? <Workspace account={account}/> : <SignIn onSignIn={async current => { await remember(current); setError(""); setAccount(current); }} />}
    <footer className="foot"><span>Folio · Examination office</span>{account && <span>{account.display_name}</span>}</footer></>;
}
