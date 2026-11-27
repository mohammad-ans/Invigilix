import React from "react";
import { createRoot } from "react-dom/client";
import { CandidateAttempt, CandidateExams, purgeDeliveryAccount } from "../../../frontend/src/features/delivery/pages.jsx";

const accountId = sessionStorage.getItem("fixture-account-id") || "fixture-account";
const attemptId = location.pathname.match(/^\/attempts\/([^/]+)\/?$/)?.[1];
window.fixtureLogout = () => { root.unmount(); return purgeDeliveryAccount(accountId); };
const root = createRoot(document.getElementById("root"));
root.render(<><header className="appbar"><div className="bar-inner"><div className="brand"><b>Folio</b><small>Examination office</small></div>Candidate</div></header>
  {attemptId ? <CandidateAttempt accountId={accountId} attemptId={attemptId}/>
  : <CandidateExams/>}</>);
navigator.serviceWorker.register("/sw.js", {type:"module"});
