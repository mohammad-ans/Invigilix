// Route table from docs/pages.md. The platform router mounts these paths.
export const paths = {
  exams: "/examiner/exams",
  edit: id => `/examiner/exams/${id}/edit`,
  enrollment: id => `/examiner/exams/${id}/enrollment`,
  preview: id => `/examiner/exams/${id}/preview`,
  questions: "/examiner/questions",
};

/** Match a pathname against the authoring routes; returns { name, params } or null. */
export function matchRoute(pathname) {
  const clean = pathname.replace(/\/+$/, "") || "/";
  if (clean === paths.exams) return { name: "exams", params: {} };
  if (clean === paths.questions) return { name: "questions", params: {} };
  const m = clean.match(/^\/examiner\/exams\/([^/]+)\/(edit|enrollment|preview)$/);
  return m ? { name: m[2], params: { id: decodeURIComponent(m[1]) } } : null;
}
