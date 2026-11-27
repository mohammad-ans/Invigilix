// The contract every results adapter fulfils. Pages depend only on this
// interface, so the live HTTP adapter and the labelled preview adapter are
// interchangeable, and a conformance test keeps them that way.
//
// Every method returns a Promise. Failures reject with ApiError carrying
// { status, code, message, issues[{ code, message, field?, item?, row? }] }.

const abstract = name => Promise.reject(new Error(`${name} is not implemented by this adapter.`));

export class ResultsApi {
  /** "live" for real records, "preview" for fictional session-local records. */
  get mode() { throw new Error("Adapters must declare their mode."); }

  // Monitoring and announcements (FR10)
  getMonitor(examId) { return abstract("getMonitor"); }
  listAnnouncements(examId) { return abstract("listAnnouncements"); }
  postAnnouncement(examId, message) { return abstract("postAnnouncement"); }

  // Marking (FR11)
  getMarkingQueue(examId) { return abstract("getMarkingQueue"); }
  gradeWrittenItem(attemptId, slot, awardedMarks) { return abstract("gradeWrittenItem"); }

  // Review, release and analytics (FR12, SR05)
  getExamResults(examId) { return abstract("getExamResults"); }
  publishResults(examId) { return abstract("publishResults"); }

  // Reports and verification (SR02, SR06)
  downloadClassReport(examId) { return abstract("downloadClassReport"); }
  getCandidateResult(attemptId) { return abstract("getCandidateResult"); }
  downloadCandidateReport(attemptId) { return abstract("downloadCandidateReport"); }
  verifyReport(verificationCode, sha256Hex) { return abstract("verifyReport"); }
}

/** Method names that make up the interface (for conformance checks). */
export const RESULTS_API_METHODS = Object.getOwnPropertyNames(ResultsApi.prototype)
  .filter(name => name !== "constructor" && name !== "mode");
