// The contract every authoring adapter fulfils. Pages depend only on this
// interface, so the live HTTP adapter and the labelled preview adapter are
// interchangeable (and a conformance test keeps them that way).
//
// Every method returns a Promise. Failures reject with ApiError carrying
// { status, code, message, issues[{ code, message, field?, item?, row? }] }.

const abstract = name => () => Promise.reject(new Error(`${name} is not implemented by this adapter.`));

export class AuthoringApi {
  /** "live" for real records, "preview" for fictional session-local records. */
  get mode() { throw new Error("Adapters must declare their mode."); }

  // Exams (FR03, FR05)
  listExams() { return abstract("listExams")(); }
  getExam(id) { return abstract("getExam")(id); }
  createExam(details) { return abstract("createExam")(details); }
  updateExam(id, details) { return abstract("updateExam")(id, details); }
  setItems(id, items) { return abstract("setItems")(id, items); }
  publishExam(id) { return abstract("publishExam")(id); }
  previewExam(id) { return abstract("previewExam")(id); }
  duplicateExam(id) { return abstract("duplicateExam")(id); }

  // Question bank (FR04, SR04)
  searchQuestions(filters) { return abstract("searchQuestions")(filters); }
  getQuestion(id) { return abstract("getQuestion")(id); }
  createQuestion(body) { return abstract("createQuestion")(body); }
  reviseQuestion(id, body) { return abstract("reviseQuestion")(id, body); }
  importQuestions(csv, options) { return abstract("importQuestions")(csv, options); }

  // Roster (FR06, SR04)
  getRoster(id) { return abstract("getRoster")(id); }
  enroll(id, emails) { return abstract("enroll")(id, emails); }
  setEnrollment(id, candidateId, active) { return abstract("setEnrollment")(id, candidateId, active); }
  importRoster(id, csv, options) { return abstract("importRoster")(id, csv, options); }

  // Candidate accounts (SR04, administrators). A committing import returns each
  // new account's initial credential exactly once.
  importCandidates(csv, options) { return abstract("importCandidates")(csv, options); }
}

/** Method names that make up the interface (for conformance checks). */
export const AUTHORING_API_METHODS = Object.getOwnPropertyNames(AuthoringApi.prototype)
  .filter(name => name !== "constructor" && name !== "mode");

/** Particulars request body from an exam response, with optional overrides. */
export function detailsBody(exam, overrides = {}) {
  const { title, instructions, opens_at, closes_at, duration_minutes, total_marks, shuffle_questions, shuffle_choices } = exam;
  return { title, instructions, opens_at, closes_at, duration_minutes, total_marks, shuffle_questions, shuffle_choices, ...overrides };
}
