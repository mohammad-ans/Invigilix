// Public surface of the results feature for the platform router.
import "./results.css";
import MonitorPage from "./pages/MonitorPage.jsx";
import MarkingPage from "./pages/MarkingPage.jsx";
import ResultsPage from "./pages/ResultsPage.jsx";
import CandidateResultPage from "./pages/CandidateResultPage.jsx";
import VerifyPage from "./pages/VerifyPage.jsx";

export {
  CandidateResultPage,
  MarkingPage,
  MonitorPage,
  ResultsPage,
  VerifyPage,
};
export { ResultsApi, RESULTS_API_METHODS } from "./api/ResultsApi.js";
export { ApiError, HttpResultsApi } from "./api/HttpResultsApi.js";
export { FixtureResultsApi, SAMPLE_VERIFICATION_CODE } from "./api/FixtureResultsApi.js";
export { matchRoute, paths } from "./paths.js";
export * from "./domain/rules.js";

export const resultsRoutes = [
  { name: "monitor", path: "/examiner/exams/:id/monitor", Page: MonitorPage, title: "Examination monitor" },
  { name: "marking", path: "/examiner/exams/:id/marking", Page: MarkingPage, title: "Written marking" },
  { name: "results", path: "/examiner/exams/:id/results", Page: ResultsPage, title: "Results & analytics" },
  { name: "candidateResult", path: "/me/attempts/:id/result", Page: CandidateResultPage, title: "Released result" },
  { name: "verify", path: "/verify", Page: VerifyPage, title: "Verify report" },
];
