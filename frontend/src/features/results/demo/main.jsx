// Feature-local preview harness using FixtureResultsApi with hash routing.
import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "../../../design/folio.css";
import {
  FixtureResultsApi,
  matchRoute,
  paths,
  resultsRoutes,
} from "../index.js";

const DEFAULT_PATH = paths.monitor("exam-bio-204");
const currentPath = () => window.location.hash.slice(1) || DEFAULT_PATH;

function ResultsDemoShell() {
  const api = useMemo(() => new FixtureResultsApi(), []);
  const [path, setPath] = useState(currentPath);

  useEffect(() => {
    const onHash = () => {
      setPath(currentPath());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const navigate = to => {
    window.location.hash = to;
  };
  const match = matchRoute(path);
  const route = resultsRoutes.find(r => r.name === match?.name);

  useEffect(() => {
    document.title = `${route?.title ?? "Not found"} · Folio`;
  }, [route]);

  const navLinks = [
    { label: "Monitor", to: paths.monitor("exam-bio-204"), name: "monitor" },
    { label: "Marking", to: paths.marking("exam-bio-204"), name: "marking" },
    { label: "Results", to: paths.results("exam-bio-204"), name: "results" },
    { label: "Candidate result", to: paths.candidateResult("att-sana-released"), name: "candidateResult" },
    { label: "Verify PDF", to: paths.verify, name: "verify" },
  ];

  return (
    <>
      <header className="appbar">
        <div className="bar-inner">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
            <b>Folio</b>
            <small>Examination office</small>
          </div>
          <nav className="res-demo-nav" aria-label="Results preview navigation">
            {navLinks.map(item => (
              <a
                key={item.name}
                href={"#" + item.to}
                aria-current={match?.name === item.name ? "page" : undefined}
              >
                {item.label}
              </a>
            ))}
          </nav>
        </div>
      </header>
      {route ? (
        <route.Page key={path} api={api} params={match.params} navigate={navigate} />
      ) : (
        <main className="shell">
          <h1>Page not found</h1>
          <p>
            <a href={"#" + DEFAULT_PATH}>Return to examination monitor</a>
          </p>
        </main>
      )}
      <footer className="foot">
        <span>Folio · Results preview</span>
        <span>Fictional records · session only</span>
      </footer>
    </>
  );
}

const navStyle = document.createElement("style");
navStyle.textContent = `.res-demo-nav{display:flex;flex-wrap:wrap;gap:4px}.res-demo-nav a{color:#d9e6d9;text-decoration:none;font:600 13px var(--sans);padding:8px 10px;border-radius:3px}.res-demo-nav a[aria-current=page]{background:#234b40;color:var(--sheet);box-shadow:inset 0 -2px 0 #abc6a6}.res-demo-nav a:hover{color:var(--sheet)}@media(max-width:520px){.res-demo-nav a{padding:6px 7px;font-size:12px}}`;
document.head.append(navStyle);

createRoot(document.getElementById("root")).render(<ResultsDemoShell />);
