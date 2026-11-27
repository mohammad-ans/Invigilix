// Preview/fixture adapter for the results feature using fictional in-memory records.
// Mirrors HttpResultsApi signatures and error shapes so UI states (empty, stale,
// pending release, validation, valid/invalid verification) work offline.
import { ApiError } from "./HttpResultsApi.js";
import {
  sha256HexFromBuffer,
  validateAnnouncementInput,
  validateAwardInput,
  validateVerifyInputs,
} from "../domain/rules.js";

const clone = v => JSON.parse(JSON.stringify(v));
const fail = (status, code, message, issues = []) => {
  throw new ApiError(status, { error: { code, message, issues } });
};

function buildSamplePdfBytes(text) {
  const safe = text.replace(/[()\\]/g, "");
  const body = `%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R >> endobj\n4 0 obj << /Length ${safe.length + 34} >> stream\nBT /F1 12 Tf 48 760 Td (${safe}) Tj ET\nendstream endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n`;
  return new TextEncoder().encode(body);
}

const SAMPLE_VERIFICATION_CODE = "FOL-AT09-9f8e7d6c5b4a321098765432";
const SAMPLE_PDF_BYTES = buildSamplePdfBytes(
  `Folio Official Candidate Result | Field ecology | Sana Ali | 7.00 / 10.00 | ${SAMPLE_VERIFICATION_CODE}`
);

export class FixtureResultsApi {
  mode = "preview";

  constructor() {
    const now = new Date("2026-11-27T10:48:00Z");
    const iso = mins => new Date(now.getTime() + mins * 60_000).toISOString();

    this._reports = new Map();
    this._sampleDigestReady = (globalThis.crypto?.subtle
      ? sha256HexFromBuffer(SAMPLE_PDF_BYTES.buffer)
      : Promise.resolve("a".repeat(64))
    ).then(hex => {
      this._reports.set(SAMPLE_VERIFICATION_CODE, {
        verification_code: SAMPLE_VERIFICATION_CODE,
        sha256_hex: hex,
        pdf_bytes: SAMPLE_PDF_BYTES,
      });
      if (this._candidateResults["att-sana-released"]) {
        this._candidateResults["att-sana-released"].sha256_hex = hex;
      }
      if (this._results["exam-released"]) {
        this._results["exam-released"].attempts[0].verification_code = SAMPLE_VERIFICATION_CODE;
      }
      return hex;
    });

    this._monitors = {
      "exam-bio-204": {
        exam_id: "exam-bio-204",
        exam_title: "Field ecology",
        status: "ongoing",
        opens_at: iso(-18),
        closes_at: iso(12),
        published_at: iso(-60),
        results_published_at: null,
        server_time: now.toISOString(),
        total_items: 8,
        counts: { enrolled: 4, not_started: 0, in_progress: 3, submitted: 1, expired: 0, finalized: 1 },
        roster: [
          {
            candidate_id: "cand-nora",
            display_name: "Nora Khan",
            email: "nora.khan@example.test",
            enrollment_active: true,
            attempt_id: "att-nora",
            status: "working",
            answered_count: 3,
            total_items: 8,
            started_at: iso(-15),
            deadline_at: iso(12),
            finalized_at: null,
            close_reason: null,
            last_saved_at: iso(-2),
            incident_count: 0,
          },
          {
            candidate_id: "cand-eli",
            display_name: "Eli Brooks",
            email: "eli.brooks@example.test",
            enrollment_active: true,
            attempt_id: "att-eli",
            status: "reconnected",
            answered_count: 5,
            total_items: 8,
            started_at: iso(-16),
            deadline_at: iso(12),
            finalized_at: null,
            close_reason: null,
            last_saved_at: iso(-1),
            incident_count: 1,
          },
          {
            candidate_id: "cand-sana",
            display_name: "Sana Ali",
            email: "sana.ali@example.test",
            enrollment_active: true,
            attempt_id: "att-sana",
            status: "submitted",
            answered_count: 8,
            total_items: 8,
            started_at: iso(-17),
            deadline_at: iso(12),
            finalized_at: iso(-3),
            close_reason: "submitted",
            last_saved_at: iso(-3),
            incident_count: 0,
          },
          {
            candidate_id: "cand-remy",
            display_name: "Remy Chen",
            email: "remy.chen@example.test",
            enrollment_active: true,
            attempt_id: "att-remy",
            status: "working",
            answered_count: 6,
            total_items: 8,
            started_at: iso(-14),
            deadline_at: iso(12),
            finalized_at: null,
            close_reason: null,
            last_saved_at: iso(-1),
            incident_count: 0,
          },
        ],
        incidents: [
          {
            id: "ev-1",
            attempt_id: "att-eli",
            candidate_id: "cand-eli",
            candidate_name: "Eli Brooks",
            kind: "reconnected",
            recorded_at: iso(-6),
            note: "Eli Brooks reconnected. Saved progress restored.",
          },
        ],
        announcements: [],
      },
      "exam-empty": {
        exam_id: "exam-empty",
        exam_title: "Botany baseline (empty)",
        status: "scheduled",
        opens_at: iso(20),
        closes_at: iso(50),
        published_at: iso(-10),
        results_published_at: null,
        server_time: now.toISOString(),
        total_items: 3,
        counts: { enrolled: 0, not_started: 0, in_progress: 0, submitted: 0, expired: 0, finalized: 0 },
        roster: [],
        incidents: [],
        announcements: [],
      },
    };

    this._marking = {
      "exam-bio-204": {
        exam_id: "exam-bio-204",
        exam_title: "Field ecology",
        status: "closed",
        results_published_at: null,
        unfinalized_attempts: 0,
        pending_written_count: 1,
        graded_written_count: 0,
        items: [
          {
            attempt_id: "att-sana",
            candidate_id: "cand-sana",
            candidate_name: "Sana Ali",
            candidate_email: "sana.ali@example.test",
            slot: 3,
            display_no: 3,
            topic: "Sampling",
            difficulty: "hard",
            prompt: "Why would you repeat the survey on a second transect?",
            rubric: "Award up to 4.00 for explaining habitat representativeness, spatial replication, and reducing sampling variance.",
            written_answer: "Repeating the survey across a second transect checks whether cover gradients hold across microhabitats and reduces chance bias from one path.",
            max_marks: "4.00",
            awarded_marks: null,
            graded_by: null,
            graded_by_name: null,
            finalized_at: iso(-3),
            close_reason: "submitted",
          },
        ],
      },
      "exam-empty": {
        exam_id: "exam-empty",
        exam_title: "Botany baseline (empty)",
        status: "scheduled",
        results_published_at: null,
        unfinalized_attempts: 0,
        pending_written_count: 0,
        graded_written_count: 0,
        items: [],
      },
    };

    this._results = {
      "exam-bio-204": {
        exam_id: "exam-bio-204",
        exam_title: "Field ecology",
        status: "closed",
        opens_at: iso(-60),
        closes_at: iso(-5),
        total_marks: "10.00",
        published_at: iso(-120),
        results_published_at: null,
        server_time: now.toISOString(),
        can_release: false,
        release_blockers: [
          {
            code: "grading_incomplete",
            message: "Attempt att-sana slot 3 still awaits a manual grade.",
            field: "awarded_marks",
            item: 3,
          },
        ],
        summary: {
          enrolled_count: 3,
          finalized_count: 2,
          in_progress_count: 0,
          no_show_count: 1,
          graded_attempt_count: 1,
          pending_grading_count: 1,
          mean_score: "4.00",
          median_score: "4.00",
          min_score: "4.00",
          max_score: "4.00",
        },
        attempts: [
          {
            attempt_id: "att-sana",
            candidate_id: "cand-sana",
            display_name: "Sana Ali",
            email: "sana.ali@example.test",
            close_reason: "submitted",
            finalized_at: iso(-10),
            graded_count: 2,
            item_count: 3,
            total_score: null,
            max_marks: "10.00",
            status: "pending_grade",
            verification_code: null,
          },
          {
            attempt_id: "att-nora",
            candidate_id: "cand-nora",
            display_name: "Nora Khan",
            email: "nora.khan@example.test",
            close_reason: "expired",
            finalized_at: iso(-5),
            graded_count: 3,
            item_count: 3,
            total_score: "4.00",
            max_marks: "10.00",
            status: "graded",
            verification_code: null,
          },
        ],
        question_analytics: [
          {
            slot: 1,
            question_id: "q-1",
            version_id: "qv-1",
            version_no: 1,
            topic: "Ecology",
            difficulty: "easy",
            kind: "single",
            prompt: "Which factor is the light level measured in this study?",
            max_marks: "2.00",
            exposure_count: 2,
            skipped_count: 1,
            skip_rate: 0.5,
            skip_rate_display: "1/2",
            graded_exposure_count: 2,
            observed_facility: "0.50",
            facility_display: "0.50",
            common_incorrect_selections: [],
          },
          {
            slot: 2,
            question_id: "q-2",
            version_id: "qv-2",
            version_no: 1,
            topic: "Diversity",
            difficulty: "medium",
            kind: "multiple",
            prompt: "Which measurements describe species diversity?",
            max_marks: "4.00",
            exposure_count: 2,
            skipped_count: 0,
            skip_rate: 0,
            skip_rate_display: "0/2",
            graded_exposure_count: 2,
            observed_facility: "0.75",
            facility_display: "0.75",
            common_incorrect_selections: [
              { option_no: 3, label: "Air temperature alone", count: 1, exposure_count: 2 },
            ],
          },
          {
            slot: 3,
            question_id: "q-3",
            version_id: "qv-3",
            version_no: 1,
            topic: "Sampling",
            difficulty: "hard",
            kind: "written",
            prompt: "Why would you repeat the survey on a second transect?",
            max_marks: "4.00",
            exposure_count: 2,
            skipped_count: 1,
            skip_rate: 0.5,
            skip_rate_display: "1/2",
            graded_exposure_count: 1,
            observed_facility: "0.00",
            facility_display: "0.00",
            common_incorrect_selections: [],
          },
        ],
      },
      "exam-empty": {
        exam_id: "exam-empty",
        exam_title: "Botany baseline (empty)",
        status: "scheduled",
        opens_at: iso(20),
        closes_at: iso(50),
        total_marks: "10.00",
        published_at: iso(-10),
        results_published_at: null,
        server_time: now.toISOString(),
        can_release: false,
        release_blockers: [
          {
            code: "exam_not_closed",
            message: "Results cannot be released until the scheduled exam close time has passed.",
            field: "closes_at",
          },
        ],
        summary: {
          enrolled_count: 2,
          finalized_count: 0,
          in_progress_count: 0,
          no_show_count: 2,
          graded_attempt_count: 0,
          pending_grading_count: 0,
          mean_score: null,
          median_score: null,
          min_score: null,
          max_score: null,
        },
        attempts: [],
        question_analytics: [
          {
            slot: 1,
            question_id: "q-empty-1",
            version_id: "qv-empty-1",
            version_no: 1,
            topic: "Sampling",
            difficulty: "medium",
            kind: "single",
            prompt: "What should stay constant between quadrats?",
            max_marks: "4.00",
            exposure_count: 0,
            skipped_count: 0,
            skip_rate: null,
            skip_rate_display: "No data",
            graded_exposure_count: 0,
            observed_facility: null,
            facility_display: "No data",
            common_incorrect_selections: [],
          },
        ],
      },
    };

    this._candidateResults = {
      "att-sana-released": {
        attempt_id: "att-sana-released",
        exam_id: "exam-bio-204",
        exam_title: "Field ecology",
        candidate_id: "cand-sana",
        candidate_name: "Sana Ali",
        finalized_at: iso(-20),
        close_reason: "submitted",
        results_published_at: iso(-2),
        total_score: "7.00",
        max_marks: "10.00",
        verification_code: SAMPLE_VERIFICATION_CODE,
        sha256_hex: "",
        report_download_path: "/me/attempts/att-sana-released/report",
        items: [
          {
            slot: 1,
            display_no: 1,
            kind: "single",
            prompt: "Which factor is the light level measured in this study?",
            max_marks: "2.00",
            awarded_marks: "2.00",
            flagged: false,
            written_answer: null,
            selected_options: [{ option_no: 1, label: "An abiotic factor" }],
          },
          {
            slot: 2,
            display_no: 2,
            kind: "multiple",
            prompt: "Which measurements describe species diversity?",
            max_marks: "4.00",
            awarded_marks: "2.00",
            flagged: false,
            written_answer: null,
            selected_options: [{ option_no: 1, label: "Species richness" }],
          },
          {
            slot: 3,
            display_no: 3,
            kind: "written",
            prompt: "Why would you repeat the survey on a second transect?",
            max_marks: "4.00",
            awarded_marks: "3.00",
            flagged: true,
            written_answer: "Repeating the survey across a second transect checks whether cover gradients hold across microhabitats.",
            selected_options: [],
          },
        ],
      },
    };
  }

  async getMonitor(examId) {
    const mon = this._monitors[examId];
    if (!mon) fail(404, "not_found", "Exam was not found.");
    mon.server_time = new Date().toISOString();
    return clone(mon);
  }

  async listAnnouncements(examId) {
    const mon = this._monitors[examId];
    if (!mon) fail(404, "not_found", "Exam was not found.");
    return clone(mon.announcements);
  }

  async postAnnouncement(examId, message) {
    const mon = this._monitors[examId];
    if (!mon) fail(404, "not_found", "Exam was not found.");
    const check = validateAnnouncementInput(message);
    if (check.issue) fail(422, "validation_failed", "The request has invalid fields.", [check.issue]);
    const entry = {
      id: "ann-" + (mon.announcements.length + 1),
      exam_id: examId,
      author_id: "examiner-1",
      author_name: "Remy Chen (preview)",
      posted_at: new Date().toISOString(),
      message: check.value,
    };
    mon.announcements.unshift(entry);
    return clone(entry);
  }

  async getMarkingQueue(examId) {
    const q = this._marking[examId];
    if (!q) fail(404, "not_found", "Exam was not found.");
    return clone(q);
  }

  async gradeWrittenItem(attemptId, slot, awardedMarks) {
    for (const examId of Object.keys(this._marking)) {
      const q = this._marking[examId];
      const item = q.items.find(it => it.attempt_id === attemptId && Number(it.slot) === Number(slot));
      if (!item) continue;
      if (q.results_published_at) {
        fail(409, "results_already_released", "Results have been released and awards are now frozen.");
      }
      const check = validateAwardInput(awardedMarks, item.max_marks);
      if (check.issue) fail(422, "validation_failed", "The request has invalid fields.", [check.issue]);
      item.awarded_marks = check.value;
      item.graded_by = "examiner-1";
      item.graded_by_name = "Remy Chen";
      q.pending_written_count = q.items.filter(it => it.awarded_marks === null).length;
      q.graded_written_count = q.items.filter(it => it.awarded_marks !== null).length;

      const res = this._results[examId];
      const attRow = res?.attempts.find(a => a.attempt_id === attemptId);
      const total = (4 + Number(check.value)).toFixed(2);
      if (attRow) {
        attRow.graded_count = 3;
        attRow.total_score = total;
        attRow.status = "graded";
        res.summary.graded_attempt_count = res.attempts.filter(a => a.total_score !== null).length;
        res.summary.pending_grading_count = res.attempts.length - res.summary.graded_attempt_count;
        const scores = res.attempts.map(a => a.total_score).filter(Boolean).map(Number);
        if (scores.length) {
          res.summary.mean_score = (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(2);
          res.summary.min_score = Math.min(...scores).toFixed(2);
          res.summary.max_score = Math.max(...scores).toFixed(2);
          res.summary.median_score = res.summary.mean_score;
        }
        res.release_blockers = q.pending_written_count === 0 ? [] : res.release_blockers;
        res.can_release = res.release_blockers.length === 0;
      }

      return {
        attempt_id: attemptId,
        exam_id: examId,
        slot: Number(slot),
        awarded_marks: check.value,
        max_marks: item.max_marks,
        graded_by: "examiner-1",
        graded_count: 3,
        item_count: 3,
        attempt_total_score: total,
      };
    }
    fail(404, "not_found", "Attempt item was not found.");
  }

  async getExamResults(examId) {
    await this._sampleDigestReady;
    const res = this._results[examId];
    if (!res) fail(404, "not_found", "Exam was not found.");
    return clone(res);
  }

  async publishResults(examId) {
    await this._sampleDigestReady;
    const res = this._results[examId];
    if (!res) fail(404, "not_found", "Exam was not found.");
    if (res.results_published_at) {
      fail(409, "results_already_released", "Results have already been released for this exam.");
    }
    if (!res.can_release) {
      const b = res.release_blockers[0];
      fail(409, b.code, b.message, res.release_blockers);
    }
    const ts = new Date().toISOString();
    res.results_published_at = ts;
    res.status = "results_released";
    res.attempts.forEach(a => {
      a.status = "released";
      a.verification_code = a.verification_code || SAMPLE_VERIFICATION_CODE;
    });
    if (this._marking[examId]) {
      this._marking[examId].results_published_at = ts;
      this._marking[examId].status = "results_released";
    }
    return clone(res);
  }

  async downloadClassReport(examId) {
    const res = this._results[examId];
    if (!res) fail(404, "not_found", "Exam was not found.");
    const bytes = buildSamplePdfBytes(`Folio Class Summary | ${res.exam_title} | Mean ${res.summary.mean_score ?? "No data"}`);
    return {
      filename: `exam-${examId}-summary.pdf`,
      blob: new Blob([bytes], { type: "application/pdf" }),
    };
  }

  async getCandidateResult(attemptId) {
    await this._sampleDigestReady;
    if (attemptId === "att-pending") {
      fail(404, "not_found", "Result was not found.");
    }
    const res = this._candidateResults[attemptId];
    if (!res) fail(404, "not_found", "Result was not found.");
    return clone(res);
  }

  async downloadCandidateReport(attemptId) {
    await this._sampleDigestReady;
    if (!this._candidateResults[attemptId]) fail(404, "not_found", "Report was not found.");
    return {
      filename: `result-${attemptId}.pdf`,
      blob: new Blob([SAMPLE_PDF_BYTES], { type: "application/pdf" }),
    };
  }

  async verifyReport(verificationCode, sha256Hex) {
    await this._sampleDigestReady;
    const check = validateVerifyInputs(verificationCode, sha256Hex);
    if (check.issues) fail(422, "validation_failed", "The request has invalid fields.", check.issues);
    const rec = this._reports.get(check.code);
    return { valid: Boolean(rec && rec.sha256_hex === check.digest) };
  }
}

export { SAMPLE_VERIFICATION_CODE };
