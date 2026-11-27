// Route paths and matcher for the results feature (docs/pages.md).

export const paths = {
  monitor: examId => `/examiner/exams/${examId}/monitor`,
  marking: examId => `/examiner/exams/${examId}/marking`,
  results: examId => `/examiner/exams/${examId}/results`,
  candidateResult: attemptId => `/me/attempts/${attemptId}/result`,
  verify: "/verify",
};

const PATTERNS = [
  ["monitor", /^\/examiner\/exams\/([^/]+)\/monitor\/?$/, m => ({ id: decodeURIComponent(m[1]) })],
  ["marking", /^\/examiner\/exams\/([^/]+)\/marking\/?$/, m => ({ id: decodeURIComponent(m[1]) })],
  ["results", /^\/examiner\/exams\/([^/]+)\/results\/?$/, m => ({ id: decodeURIComponent(m[1]) })],
  ["candidateResult", /^\/me\/attempts\/([^/]+)\/result\/?$/, m => ({ id: decodeURIComponent(m[1]) })],
  ["verify", /^\/verify\/?$/, () => ({})],
];

export function matchRoute(pathname) {
  const clean = String(pathname || "/").split("?")[0];
  for (const [name, pattern, extract] of PATTERNS) {
    const match = clean.match(pattern);
    if (match) return { name, params: extract(match) };
  }
  return null;
}
