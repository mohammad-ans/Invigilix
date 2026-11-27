// Feature-local preview harness: `npm run dev`, then open
// /src/features/authoring/demo/index.html. It mounts the authoring pages on
// fictional records with hash routing. The platform shell and router replace
// this in production; nothing here is imported by the feature itself.
import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "../../../design/folio.css";
import { CandidateImportPanel, FixtureAuthoringApi, authoringRoutes, matchRoute, paths } from "../index.js";
import { PageHead } from "../../../design/Folio.jsx";

const ADMIN_IMPORT = "/admin/accounts/import";

const current = () => (window.location.hash.slice(1) || paths.exams);

function Harness() {
  const api = useMemo(() => new FixtureAuthoringApi(), []);
  const [path, setPath] = useState(current);
  useEffect(() => {
    const sync = () => { setPath(current()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  const navigate = to => { window.location.hash = to; };
  const match = matchRoute(path);
  const route = authoringRoutes.find(r => r.name === match?.name);
  useEffect(() => { document.title = `${route?.title ?? "Not found"} · Folio`; }, [route]);
  const section = path === ADMIN_IMPORT ? "admin" : match?.name === "questions" ? "questions" : "exams";

  return <>
    <header className="appbar"><div className="bar-inner">
      <div className="brand"><span className="brand-mark" aria-hidden="true"><i /><i /><i /></span><b>Folio</b><small>Examination office</small></div>
      <nav className="au-nav" aria-label="Authoring">
        <a href={"#" + paths.exams} aria-current={section === "exams" ? "page" : undefined}>Exams</a>
        <a href={"#" + paths.questions} aria-current={section === "questions" ? "page" : undefined}>Question bank</a>
        <a href={"#" + ADMIN_IMPORT} aria-current={section === "admin" ? "page" : undefined}>Admin import</a>
      </nav>
    </div></header>
    {path === ADMIN_IMPORT ? <main className="shell au-page">
        <PageHead crumb="Administration" title="Import candidates" details={<><b>Accounts</b><i />Embedded in the foundation's account page in production</>} />
        <section className="board"><CandidateImportPanel api={api} /></section>
      </main>
    : route ? <route.Page key={path} api={api} params={match.params} navigate={navigate} />
      : <main className="shell"><h1>Page not found</h1><p><a href={"#" + paths.exams}>Return to the exam register</a></p></main>}
    <footer className="foot"><span>Folio · Authoring preview</span><span>Fictional records · session only</span></footer>
  </>;
}

const style = document.createElement("style");
style.textContent = `.au-nav{display:flex;gap:4px}.au-nav a{color:#d9e6d9;text-decoration:none;font:600 13px var(--sans);padding:8px 12px;border-radius:3px}
.au-nav a[aria-current=page]{background:#234b40;color:var(--sheet);box-shadow:inset 0 -2px 0 #abc6a6}.au-nav a:hover{color:var(--sheet)}
@media(max-width:520px){.au-nav a{padding:6px 8px;font-size:12px}}`;
document.head.append(style);
createRoot(document.getElementById("root")).render(<Harness />);
