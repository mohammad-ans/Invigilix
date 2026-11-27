// Production adapter: same-origin JSON over the FastAPI authoring router.
// The platform supplies the API prefix and CSRF header. Session cookies are
// HttpOnly and travel automatically; nothing private is cached (no-store).

export class ApiError extends Error {
  constructor(status, body) {
    const error = body?.error ?? {};
    super(error.message || `Request failed (${status}).`);
    this.status = status;
    this.code = error.code || (status === 0 ? "network" : "unknown");
    this.issues = error.issues ?? [];
  }
  get isValidation() { return this.status === 422; }
  get isConflict() { return this.status === 409; }
}

const readCookie = name => document.cookie.split("; ").find(c => c.startsWith(name + "="))?.split("=")[1];

export class HttpAuthoringApi {
  mode = "live";

  constructor({ baseUrl = "/api", fetchImpl = (...a) => fetch(...a), csrfHeader = () => ({ "X-CSRF-Token": readCookie("csrf_token") ?? "" }) } = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.fetch = fetchImpl;
    this.csrfHeader = csrfHeader;
  }

  async request(method, path, { json, csv, query } = {}) {
    const url = new URL(this.baseUrl + path, window.location.origin);
    Object.entries(query ?? {}).forEach(([k, v]) => { if (v !== undefined && v !== "" && v !== null) url.searchParams.set(k, v); });
    const headers = { Accept: "application/json" };
    if (method !== "GET") Object.assign(headers, this.csrfHeader());
    let body;
    if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
    if (csv !== undefined) { headers["Content-Type"] = "text/csv; charset=utf-8"; body = csv; }
    let response;
    try {
      response = await this.fetch(url, { method, headers, body, credentials: "same-origin", cache: "no-store" });
    } catch {
      throw new ApiError(0, { error: { code: "network", message: "The server could not be reached. Check your connection and try again." } });
    }
    const data = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) throw new ApiError(response.status, data);
    return data;
  }

  // Exams (FR03, FR05)
  listExams() { return this.request("GET", "/exams"); }
  getExam(id) { return this.request("GET", `/exams/${id}`); }
  createExam(details) { return this.request("POST", "/exams", { json: details }); }
  updateExam(id, details) { return this.request("PUT", `/exams/${id}`, { json: details }); }
  setItems(id, items) { return this.request("PUT", `/exams/${id}/items`, { json: { items } }); }
  publishExam(id) { return this.request("POST", `/exams/${id}/publish`); }
  previewExam(id) { return this.request("POST", `/exams/${id}/preview`); }

  // Question bank (FR04)
  searchQuestions(filters = {}) { return this.request("GET", "/questions", { query: filters }); }
  getQuestion(id) { return this.request("GET", `/questions/${id}`); }
  createQuestion(body) { return this.request("POST", "/questions", { json: body }); }
  reviseQuestion(id, body) { return this.request("POST", `/questions/${id}/versions`, { json: body }); }
  importQuestions(csv, { dryRun = false } = {}) { return this.request("POST", "/questions/import", { csv, query: { dry_run: dryRun || undefined } }); }

  // Roster (FR06, SR04)
  getRoster(id) { return this.request("GET", `/exams/${id}/enrollments`); }
  enroll(id, emails) { return this.request("POST", `/exams/${id}/enrollments`, { json: { candidate_emails: emails } }); }
  setEnrollment(id, candidateId, active) { return this.request("PATCH", `/exams/${id}/enrollments/${candidateId}`, { json: { active } }); }
  importRoster(id, csv, { dryRun = false } = {}) { return this.request("POST", `/exams/${id}/enrollments/import`, { csv, query: { dry_run: dryRun || undefined } }); }
}
