// Production HTTP adapter for the results FastAPI router.
// Keeps private payloads out of caches (cache: "no-store") and carries CSRF
// headers on cookie-authenticated mutations.

export class ApiError extends Error {
  constructor(status, body) {
    const err = body?.error ?? {};
    super(err.message || `Request failed (${status}).`);
    this.status = status;
    this.code = err.code || (status === 0 ? "network" : "unknown");
    this.issues = err.issues ?? [];
  }
  get isValidation() { return this.status === 422; }
  get isConflict() { return this.status === 409; }
  get isDenied() { return this.status === 401 || this.status === 403 || this.status === 404; }
}

const readCookie = name =>
  typeof document === "undefined"
    ? undefined
    : document.cookie.split("; ").find(c => c.startsWith(name + "="))?.split("=")[1];

function filenameFromDisposition(header, fallback) {
  const match = String(header ?? "").match(/filename="?([^";]+)"?/i);
  return match ? match[1] : fallback;
}

export class HttpResultsApi {
  mode = "live";

  constructor({
    baseUrl = "/api",
    fetchImpl = (...args) => fetch(...args),
    csrfHeader = () => ({ "X-CSRF-Token": readCookie("csrf_token") ?? "" }),
  } = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.fetch = fetchImpl;
    this.csrfHeader = csrfHeader;
  }

  async #request(method, path, { json, includeAuth = true, binary = false, fallbackFilename = "report.pdf" } = {}) {
    const headers = { Accept: binary ? "application/pdf" : "application/json" };
    if (includeAuth && method !== "GET") {
      Object.assign(headers, this.csrfHeader());
    }
    let body;
    if (json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(json);
    }

    let response;
    try {
      response = await this.fetch(this.baseUrl + path, {
        method,
        headers,
        body,
        credentials: includeAuth ? "same-origin" : "omit",
        cache: "no-store",
      });
    } catch {
      throw new ApiError(0, {
        error: {
          code: "network",
          message: "The server could not be reached. Check your connection and try again.",
        },
      });
    }

    if (!response.ok) {
      const errBody = await response.json().catch(() => null);
      throw new ApiError(response.status, errBody);
    }

    if (binary) {
      const blob = await response.blob();
      const filename = filenameFromDisposition(response.headers.get("Content-Disposition"), fallbackFilename);
      return { blob, filename };
    }
    return response.status === 204 ? null : await response.json();
  }

  // Monitoring & Announcements (FR10)
  getMonitor(examId) {
    return this.#request("GET", `/exams/${encodeURIComponent(examId)}/monitor`);
  }
  listAnnouncements(examId) {
    return this.#request("GET", `/exams/${encodeURIComponent(examId)}/announcements`);
  }
  postAnnouncement(examId, message) {
    return this.#request("POST", `/exams/${encodeURIComponent(examId)}/announcements`, {
      json: { message },
    });
  }

  // Manual Grading (FR11)
  getMarkingQueue(examId) {
    return this.#request("GET", `/exams/${encodeURIComponent(examId)}/marking`);
  }
  gradeWrittenItem(attemptId, slot, awardedMarks) {
    return this.#request(
      "PUT",
      `/attempts/${encodeURIComponent(attemptId)}/items/${encodeURIComponent(slot)}/grade`,
      { json: { awarded_marks: String(awardedMarks) } }
    );
  }

  // Results, Analytics & Release (FR12, SR05)
  getExamResults(examId) {
    return this.#request("GET", `/exams/${encodeURIComponent(examId)}/results`);
  }
  publishResults(examId) {
    return this.#request("POST", `/exams/${encodeURIComponent(examId)}/results/publish`);
  }
  downloadClassReport(examId) {
    return this.#request("GET", `/exams/${encodeURIComponent(examId)}/report`, {
      binary: true,
      fallbackFilename: `exam-${examId}-summary.pdf`,
    });
  }

  // Candidate Result & PDF (FR12, SR02)
  getCandidateResult(attemptId) {
    return this.#request("GET", `/me/attempts/${encodeURIComponent(attemptId)}/result`);
  }
  downloadCandidateReport(attemptId) {
    return this.#request("GET", `/me/attempts/${encodeURIComponent(attemptId)}/report`, {
      binary: true,
      fallbackFilename: `result-${attemptId}.pdf`,
    });
  }

  // Public Verification (SR06)
  verifyReport(verificationCode, sha256Hex) {
    return this.#request("POST", "/reports/verify", {
      json: { verification_code: verificationCode, sha256_hex: sha256Hex },
      includeAuth: false,
    });
  }
}
