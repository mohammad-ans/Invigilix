// Public surface of the authoring feature for the platform router.
//
//   import { authoringRoutes, HttpAuthoringApi } from "./features/authoring";
//   const api = new HttpAuthoringApi({ baseUrl: "/api" });
//   authoringRoutes.map(r => <Route path={r.path} element={<r.Page api={api} params={…} navigate={…} />} />)
//
// Each page takes { api, params, navigate }. Use HttpAuthoringApi for real
// records and FixtureAuthoringApi only for the labelled theme preview.
import "./authoring.css";
import ExamRegister from "./pages/ExamRegister.jsx";
import ExamEditor from "./pages/ExamEditor.jsx";
import QuestionBank from "./pages/QuestionBank.jsx";
import RosterPage from "./pages/RosterPage.jsx";
import PreviewPage from "./pages/PreviewPage.jsx";

export { ExamRegister, ExamEditor, QuestionBank, RosterPage, PreviewPage };
export { AuthoringApi, AUTHORING_API_METHODS } from "./api/AuthoringApi.js";
export { HttpAuthoringApi, ApiError } from "./api/HttpAuthoringApi.js";
export { FixtureAuthoringApi } from "./api/FixtureAuthoringApi.js";
export { paths, matchRoute } from "./paths.js";

export const authoringRoutes = [
  { name: "exams", path: "/examiner/exams", Page: ExamRegister, title: "Exam register" },
  { name: "edit", path: "/examiner/exams/:id/edit", Page: ExamEditor, title: "Edit exam" },
  { name: "questions", path: "/examiner/questions", Page: QuestionBank, title: "Question bank" },
  { name: "enrollment", path: "/examiner/exams/:id/enrollment", Page: RosterPage, title: "Roster" },
  { name: "preview", path: "/examiner/exams/:id/preview", Page: PreviewPage, title: "Preview" },
];
