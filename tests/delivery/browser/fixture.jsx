import React from "react";
import { createRoot } from "react-dom/client";
import { CandidateAttempt, CandidateExams, purgeDeliveryAccount } from "../../../frontend/src/features/delivery/pages.jsx";

const accountId = "fixture-account";
window.fixtureLogout = () => { root.unmount(); return purgeDeliveryAccount(accountId); };
const root = createRoot(document.getElementById("root"));
root.render(<><header className="appbar"><div className="bar-inner"><div className="brand"><b>Folio</b><small>Examination office</small></div>Candidate</div></header>
  {location.pathname.startsWith("/attempts/") ? <CandidateAttempt accountId={accountId} attemptId="sample"/>
  : <CandidateExams/>}</>);
navigator.serviceWorker.register("/sw.js", {type:"module"});
