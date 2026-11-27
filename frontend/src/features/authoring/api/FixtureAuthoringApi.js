// Preview adapter: fictional records held in memory for this browser session.
// It implements the HttpAuthoringApi interface with the same response shapes
// and error bodies, so pages render identically. Nothing reaches a server.
import { AuthoringApi } from "./AuthoringApi.js";
import { ApiError } from "./HttpAuthoringApi.js";
import { parseCsv } from "../domain/csv.js";
import {
  DIFFICULTIES, KINDS, RULES_FOR_KIND, centsToMarks, detailsIssues, examState, parseMarks,
  questionIssues, reviewPublication, tally,
} from "../domain/rules.js";

const uuid = () => (globalThis.crypto?.randomUUID?.() ?? "xxxxxxxx-xxxx-4xxx-8xxx-xxxxxxxxxxxx".replace(/x/g, () => (Math.random() * 16 | 0).toString(16)));
const clone = value => JSON.parse(JSON.stringify(value));
const fail = (status, code, message, issues = []) => { throw new ApiError(status, { error: { code, message, issues } }); };
const invalid = (issues, message = "The request has invalid fields.", code = "validation_failed") => fail(422, code, message, issues);
const marks = cents => centsToMarks(cents);
const MINUTE = 60_000;

const CANDIDATES = [
  ["nora.khan@example.test", "Nora Khan"], ["eli.brooks@example.test", "Eli Brooks"],
  ["sana.ali@example.test", "Sana Ali"], ["tomas.reyes@example.test", "Tomás Reyes"],
  ["ivy.okafor@example.test", "Ivy Okafor"], ["dee.lund@example.test", "Dee Lund", false],
];
const OTHERS = [["ola.examiner@example.test", "Ola Examiner", "examiner"]];

const opt = (labels, keys) => labels.map((label, i) => ({ id: i + 1, label, correct: keys.includes(i + 1) }));
const SEED_BANK = [
  ["Ecology", "easy", "single", "Which factor is the light level measured in this study?", opt(["An abiotic factor", "A population count", "A trophic level"], [1])],
  ["Sampling", "easy", "single", "What should stay constant between quadrats?", opt(["Quadrat area", "Number of species found", "Distance to the river"], [1])],
  ["Sampling", "medium", "single", "Which method best measures the change in plant cover along this transect?", opt(["Place quadrats at regular intervals along the line.", "Count only the tallest plant in each habitat.", "Collect a single sample at the tree line."], [1])],
  ["Diversity", "medium", "multiple", "Which measurements describe species diversity?", opt(["Species richness", "Relative abundance", "Air temperature alone"], [1, 2]), "partial_no_wrong"],
  ["Sampling", "hard", "written", "Why would you repeat the survey on a second transect?", [], "manual", "Replication; representativeness of the habitat; reduces the effect of chance."],
  ["Fieldwork", "easy", "single", "Which observation belongs in a field notebook?", opt(["Measured soil moisture", "An assumed population total", "An unverified trend"], [1])],
  ["Fieldwork", "medium", "multiple", "Which records make the survey reproducible?", opt(["Quadrat size", "Sampling coordinates", "The observer’s favourite species"], [1, 2]), "exact"],
  ["Sampling", "hard", "written", "Describe one source of sampling bias in this survey.", [], "manual", "Names a concrete bias (e.g. edge effect) and how it skews cover estimates."],
  ["Soil", "medium", "single", "Which reagent indicates soil pH in the field kit?", opt(["Universal indicator", "Biuret reagent", "Iodine solution"], [1])],
  ["Soil", "hard", "written", "Explain how waterlogging changes nitrogen availability.", [], "manual", "Anaerobic conditions; denitrification; reduced nitrate."],
];

export class FixtureAuthoringApi extends AuthoringApi {
  constructor({ now = () => new Date(), latency = 120 } = {}) {
    super();
    this.now = now;
    this.latency = latency;
    this.me = { id: uuid(), email: "remy.chen@example.test", display_name: "Remy Chen", roles: ["examiner"], enabled: true };
    this.accounts = [this.me,
      ...CANDIDATES.map(([email, name, enabled = true]) => ({ id: uuid(), email, display_name: name, roles: ["candidate"], enabled })),
      ...OTHERS.map(([email, name, role]) => ({ id: uuid(), email, display_name: name, roles: [role], enabled: true }))];
    this.questions = [];
    this.exams = [];
    this.enrollments = [];
    this.#seed();
  }

  get mode() { return "preview"; }

  // ---------------------------------------------------------------- seed data
  #seed() {
    const ids = SEED_BANK.map(([topic, difficulty, kind, prompt, options, rule, rubric]) =>
      this.#storeQuestion({ topic, difficulty, kind, prompt, marking_rule: rule ?? (kind === "single" ? "exact" : "manual"), options, rubric: rubric ?? null }).id);
    // An older revision on one question shows history and an outdated pin.
    const t = this.now().getTime(), at = minutes => new Date(t + minutes * MINUTE).toISOString();
    const slot = (n, qi, m, version = 1) => {
      const q = this.questions.find(x => x.id === ids[qi]);
      return { slot: n, question_id: q.id, version_id: q.versions[version - 1].id, max_marks: m };
    };
    const exam = (title, instructions, opens, closes, duration, total, items, published, shuffle = [true, true]) => {
      const record = { id: uuid(), owner_id: this.me.id, title, instructions, opens_at: at(opens), closes_at: at(closes), duration_minutes: duration,
        total_marks: total, shuffle_questions: shuffle[0], shuffle_choices: shuffle[1], published_at: published === null ? null : at(published), items };
      this.exams.push(record);
      return record;
    };
    exam("Field ecology", "Answer every question. Use the transect figure where referenced. Calculators are not required.",
      2 * 24 * 60, 2 * 24 * 60 + 30, 30, "10.00", [slot(1, 0, "2.00"), slot(2, 3, "4.00"), slot(3, 4, "4.00")], null);
    exam("Soil chemistry", "Two sections. Show your reasoning in written answers.",
      6 * 24 * 60, 6 * 24 * 60 + 90, 75, "20.00", [slot(1, 8, "4.00"), slot(2, 9, "8.00")], null, [false, true]);
    const live = exam("Sampling methods quiz", "A short check on quadrat and transect technique.",
      -12, 48, 45, "8.00", [slot(1, 1, "2.00"), slot(2, 2, "2.00"), slot(3, 6, "4.00")], -3 * 24 * 60);
    const done = exam("Fieldwork practice paper", "Practice paper. Results are released after review.",
      -9 * 24 * 60, -9 * 24 * 60 + 60, 40, "6.00", [slot(1, 5, "2.00"), slot(2, 7, "4.00")], -12 * 24 * 60);
    const later = exam("Ecology mid-term", "Bring your field notebook. Closed book otherwise.",
      3 * 24 * 60 + 600, 3 * 24 * 60 + 720, 60, "10.00", [slot(1, 0, "2.00"), slot(2, 2, "4.00"), slot(3, 7, "4.00")], -60);
    const cands = this.accounts.filter(a => a.roles.includes("candidate"));
    for (const e of [live, done, later]) cands.slice(0, 4).forEach(c => this.enrollments.push({ exam_id: e.id, candidate_id: c.id, active: true }));
    this.enrollments.push({ exam_id: this.exams[0].id, candidate_id: cands[0].id, active: true },
      { exam_id: this.exams[0].id, candidate_id: cands[1].id, active: true },
      { exam_id: this.exams[0].id, candidate_id: cands[2].id, active: false });
    // Revise question 1 so slot 1 of "Field ecology" is pinned to an older version.
    this.#revise(this.questions.find(q => q.id === ids[0]), { ...this.#latestBody(ids[0]), prompt: "Which factor in this study is abiotic?" });
  }

  // ---------------------------------------------------------------- helpers
  async #reply(fn) {
    await new Promise(r => setTimeout(r, this.latency));
    return clone(fn());
  }
  #own(list, id, what) {
    const found = list.find(x => x.id === id && x.owner_id === this.me.id);
    if (!found) fail(404, "not_found", `${what} was not found.`);
    return found;
  }
  #storeQuestion(body, id = uuid()) {
    const question = { id, owner_id: this.me.id, versions: [] };
    this.questions.push(question);
    this.#revise(question, body);
    return question;
  }
  #normalize(body) {
    const keys = new Set(body.correct_option_ids ?? (body.options ?? []).filter(o => o.correct).map(o => o.id));
    return {
      topic: String(body.topic ?? "").trim(), difficulty: body.difficulty, kind: body.kind, prompt: String(body.prompt ?? "").trim(),
      marking_rule: body.marking_rule, rubric: String(body.rubric ?? "").trim() || null,
      options: [...(body.options ?? [])].sort((a, b) => a.id - b.id).map(o => ({ id: o.id, label: String(o.label).trim(), correct: keys.has(o.id) })),
    };
  }
  #revise(question, body) {
    const content = this.#normalize(body);
    const asApi = { ...content, correct_option_ids: content.options.filter(o => o.correct).map(o => o.id) };
    const issues = questionIssues(asApi);
    if (!DIFFICULTIES.includes(content.difficulty)) issues.push({ code: "invalid_choice", message: "Choose a difficulty.", field: "difficulty" });
    if (!KINDS.includes(content.kind)) issues.push({ code: "invalid_choice", message: "Choose a question type.", field: "kind" });
    if (issues.length) invalid(issues);
    const latest = question.versions.at(-1);
    const same = latest && JSON.stringify(this.#content(latest)) === JSON.stringify(content);
    if (same) return { version: latest, created: false };
    const version = { id: uuid(), number: question.versions.length + 1, ...content };
    question.versions.push(version);
    return { version, created: true };
  }
  #content(v) { const { id, number, ...rest } = v; return rest; }
  #latestBody(questionId) { const v = this.questions.find(q => q.id === questionId).versions.at(-1); return { ...this.#content(v) }; }
  #versionOut(v) { return { ...v, correct_option_ids: v.options.filter(o => o.correct).map(o => o.id) }; }
  #questionOut(q) { return { id: q.id, version_count: q.versions.length, latest: this.#versionOut(q.versions.at(-1)) }; }
  #findVersion(versionId) {
    for (const q of this.questions) { const v = q.versions.find(x => x.id === versionId); if (v) return { q, v }; }
    return null;
  }
  #examOut(e) {
    const now = this.now();
    const items = e.items.map(i => {
      const { q, v } = this.#findVersion(i.version_id);
      return { slot: i.slot, max_marks: i.max_marks, question_id: q.id, version: this.#versionOut(v), latest_version_number: q.versions.length, outdated: q.versions.length > v.number };
    });
    const t = tally(items, e.total_marks);
    const { owner_id, items: _, ...fields } = e;
    return { ...fields, allocated_marks: marks(t.allocated), state: examState(e, now), server_time: now.toISOString(), items, publication: reviewPublication({ ...e, items }, now) };
  }
  #details(d) {
    const issues = detailsIssues(d);
    if (issues.length) invalid(issues);
    return { title: d.title.trim(), instructions: String(d.instructions ?? "").trim(), opens_at: d.opens_at, closes_at: d.closes_at,
      duration_minutes: Number(d.duration_minutes), total_marks: marks(parseMarks(d.total_marks).cents),
      shuffle_questions: Boolean(d.shuffle_questions), shuffle_choices: Boolean(d.shuffle_choices) };
  }
  #draft(id) {
    const e = this.#own(this.exams, id, "Exam");
    if (e.published_at) fail(409, "exam_published", "This paper is published and frozen. It can no longer be edited.");
    return e;
  }
  #access(e, account, enrollment) {
    if (!account || !enrollment) return "not_enrolled";
    if (!account.enabled) return "account_disabled";
    if (!account.roles.includes("candidate")) return "not_candidate";
    if (!enrollment.active) return "enrollment_inactive";
    return { draft: "awaiting_publication", scheduled: "upcoming", ongoing: "available", completed: "completed" }[examState(e, this.now())];
  }
  #rosterOut(e) {
    const entries = this.enrollments.filter(x => x.exam_id === e.id).map(x => {
      const a = this.accounts.find(c => c.id === x.candidate_id);
      const access = this.#access(e, a, x);
      return { candidate_id: a.id, email: a.email, display_name: a.display_name, active: x.active, access, can_start: access === "available" };
    }).sort((a, b) => (a.active === b.active ? a.display_name.localeCompare(b.display_name) : a.active ? -1 : 1));
    return { exam_id: e.id, state: examState(e, this.now()), server_time: this.now().toISOString(), entries };
  }
  #candidateIssue(email, field = "candidate_email") {
    const a = this.accounts.find(x => x.email.toLowerCase() === String(email).trim().toLowerCase());
    if (!String(email).trim()) return [null, { code: "required", message: "Enter the candidate's email.", field }];
    if (!a) return [null, { code: "unknown_candidate", message: "No account uses this email.", field }];
    if (!a.roles.includes("candidate")) return [null, { code: "not_candidate", message: "This account does not hold the candidate role.", field }];
    if (!a.enabled) return [null, { code: "account_disabled", message: "This account is disabled.", field }];
    return [a, null];
  }
  #rosterOpen(e) { if (examState(e, this.now()) === "completed") fail(409, "exam_closed", "The exam has closed. Its roster is now a record."); }
  #admit(e, candidateId) {
    const existing = this.enrollments.find(x => x.exam_id === e.id && x.candidate_id === candidateId);
    if (!existing) { this.enrollments.push({ exam_id: e.id, candidate_id: candidateId, active: true }); return "created"; }
    if (!existing.active) { existing.active = true; return "updated"; }
    return "unchanged";
  }
  #runImport(csvText, required, optional, planRow, dryRun) {
    let table;
    try { table = parseCsv(csvText); } catch (e) { invalid([{ code: "malformed_csv", message: e.message, field: "file" }], "The file could not be read.", "import_invalid"); }
    const headerIssues = [
      ...required.filter(h => !table.header.includes(h)).map(h => ({ code: "missing_column", message: `Add the “${h}” column.`, field: h, row: 1 })),
      ...table.header.filter(h => !required.includes(h) && !optional.includes(h)).map(h => ({ code: "unknown_column", message: `Remove or rename the “${h}” column.`, field: h, row: 1 })),
    ];
    if (headerIssues.length) invalid(headerIssues, "The header row does not match the template.", "import_invalid");
    if (!table.rows.length) invalid([{ code: "empty_file", message: "The file has no data rows.", field: "file" }], "The file has no data rows.", "import_invalid");
    const issues = [], plans = [], seen = new Map();
    for (const r of table.rows) {
      if (r.extra) { issues.push({ code: "extra_values", message: "This row has more values than the header. Quote values that contain commas.", field: "row", row: r.row }); continue; }
      try {
        const plan = planRow(r.values);
        if (seen.has(plan.key)) { issues.push({ code: "duplicate_row", message: `Repeats row ${seen.get(plan.key)}.`, field: plan.keyField, row: r.row }); continue; }
        seen.set(plan.key, r.row); plans.push(plan);
      } catch (e) {
        if (!(e instanceof ApiError)) throw e;
        issues.push(...e.issues.map(i => ({ ...i, row: r.row })));
      }
    }
    const report = { rows: table.rows.length, created: 0, updated: 0, unchanged: 0, committed: false, issues, credentials: [] };
    plans.forEach(p => { report[p.action]++; });
    if (issues.length) {
      if (!dryRun) invalid(issues, "No rows were imported. Fix the listed rows and import the file again.", "import_invalid");
      return report;
    }
    if (!dryRun) { plans.forEach(p => p.apply?.()); report.committed = true; }
    return report;
  }

  // ---------------------------------------------------------------- exams
  listExams() {
    return this.#reply(() => this.exams.filter(e => e.owner_id === this.me.id)
      .sort((a, b) => Date.parse(b.opens_at) - Date.parse(a.opens_at))
      .map(e => {
        const out = this.#examOut(e);
        const { items, publication, server_time, ...summary } = out;
        return { ...summary, item_count: items.length, enrolled: this.enrollments.filter(x => x.exam_id === e.id && x.active).length };
      }));
  }
  getExam(id) { return this.#reply(() => this.#examOut(this.#own(this.exams, id, "Exam"))); }
  createExam(details) {
    return this.#reply(() => {
      const e = { id: uuid(), owner_id: this.me.id, ...this.#details(details), published_at: null, items: [] };
      this.exams.push(e);
      return this.#examOut(e);
    });
  }
  updateExam(id, details) {
    return this.#reply(() => { const e = this.#draft(id); Object.assign(e, this.#details(details)); return this.#examOut(e); });
  }
  setItems(id, items) {
    return this.#reply(() => {
      const e = this.#draft(id);
      const pinned = new Map(e.items.map(i => [i.question_id, i.version_id]));
      const issues = [], next = [], seen = new Set();
      items.forEach((request, index) => {
        const slot = index + 1;
        const m = parseMarks(request.max_marks);
        if (m.issue) issues.push({ ...m.issue, item: slot });
        const q = this.questions.find(x => x.id === request.question_id && x.owner_id === this.me.id);
        if (!q) { issues.push({ code: "question_unavailable", message: "This question is not in your bank.", field: "question_id", item: slot }); return; }
        if (seen.has(q.id)) issues.push({ code: "duplicate_question", message: "This bank question already appears on the paper.", field: "question_id", item: slot });
        seen.add(q.id);
        const versionId = request.version_id ?? pinned.get(q.id) ?? q.versions.at(-1).id;
        if (!q.versions.some(v => v.id === versionId)) { issues.push({ code: "unknown_version", message: "That version does not belong to this question.", field: "version_id", item: slot }); return; }
        if (!m.issue) next.push({ slot, question_id: q.id, version_id: versionId, max_marks: marks(m.cents) });
      });
      if (issues.length) invalid(issues);
      e.items = next;
      return this.#examOut(e);
    });
  }
  publishExam(id) {
    return this.#reply(() => {
      const e = this.#draft(id);
      const out = this.#examOut(e);
      if (!out.publication.ready) invalid(out.publication.checks.flatMap(c => c.issues), "The paper cannot be published yet.", "paper_invalid");
      e.published_at = this.now().toISOString();
      return this.#examOut(e);
    });
  }
  duplicateExam(id) {
    return this.#reply(() => {
      const source = this.#own(this.exams, id, "Exam");
      const copy = { ...clone(source), id: uuid(), title: `Copy of ${source.title}`.slice(0, 300), published_at: null };
      this.exams.push(copy);
      return this.#examOut(copy);
    });
  }
  previewExam(id) {
    return this.#reply(() => {
      const e = this.#examOut(this.#own(this.exams, id, "Exam"));
      const now = this.now();
      return {
        mode: "sandbox", exam_id: e.id, title: e.title, instructions: e.instructions, total_marks: e.total_marks,
        server_time: now.toISOString(), deadline_at: new Date(now.getTime() + e.duration_minutes * MINUTE).toISOString(),
        items: e.items.map((i, n) => ({ slot: i.slot, display_no: n + 1, kind: i.version.kind, prompt: i.version.prompt, max_marks: i.max_marks,
          options: i.version.options.map(o => ({ id: o.id, label: o.label })), selected_option_ids: [], written_answer: "", flagged: false, revision: 0 })),
      };
    });
  }

  // ---------------------------------------------------------------- bank
  searchQuestions({ q = "", topic = "", difficulty = "", kind = "" } = {}) {
    return this.#reply(() => this.questions.filter(x => x.owner_id === this.me.id).filter(x => {
      const v = x.versions.at(-1), text = q.trim().toLowerCase();
      return (!topic || v.topic.toLowerCase() === topic.trim().toLowerCase()) && (!difficulty || v.difficulty === difficulty)
        && (!kind || v.kind === kind) && (!text || `${v.prompt} ${v.topic}`.toLowerCase().includes(text));
    }).sort((a, b) => a.versions.at(-1).topic.localeCompare(b.versions.at(-1).topic) || a.versions.at(-1).prompt.localeCompare(b.versions.at(-1).prompt))
      .map(x => this.#questionOut(x)));
  }
  getQuestion(id) {
    return this.#reply(() => {
      const q = this.#own(this.questions, id, "Question");
      const usage = this.exams.filter(e => e.owner_id === this.me.id).flatMap(e => e.items.filter(i => i.question_id === q.id).map(i => ({
        exam_id: e.id, exam_title: e.title, slot: i.slot, version_number: q.versions.find(v => v.id === i.version_id).number, frozen: Boolean(e.published_at) })));
      return { id: q.id, versions: [...q.versions].reverse().map(v => this.#versionOut(v)), usage };
    });
  }
  createQuestion(body) { return this.#reply(() => this.#questionOut(this.#storeQuestion(body))); }
  reviseQuestion(id, body) {
    return this.#reply(() => {
      const q = this.#own(this.questions, id, "Question");
      const { created } = this.#revise(q, body);
      return { question: this.#questionOut(q), created };
    });
  }
  importQuestions(csvText, { dryRun = false } = {}) {
    const required = ["question_id", "topic", "difficulty", "kind", "prompt", "marking_rule", "options", "correct_option_ids"];
    return this.#reply(() => this.#runImport(csvText, required, ["rubric"], values => {
      const issues = [];
      const id = values.question_id;
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) invalid([{ code: "invalid_uuid", message: "Use a UUID question ID.", field: "question_id" }]);
      for (const [field, allowed] of [["difficulty", DIFFICULTIES], ["kind", KINDS], ["marking_rule", Object.values(RULES_FOR_KIND).flat()]]) {
        if (!allowed.includes(values[field]?.toLowerCase())) issues.push({ code: "invalid_choice", message: `Use one of: ${[...new Set(allowed)].join(", ")}.`, field });
      }
      let options = [], keys = [];
      try { options = JSON.parse(values.options || "[]"); if (!Array.isArray(options)) throw 0; } catch { issues.push({ code: "invalid_json", message: "Use a JSON array, e.g. [1, 2].", field: "options" }); }
      try { keys = JSON.parse(values.correct_option_ids || "[]"); if (!Array.isArray(keys)) throw 0; } catch { issues.push({ code: "invalid_json", message: "Use a JSON array, e.g. [1, 2].", field: "correct_option_ids" }); }
      if (issues.length) invalid(issues);
      const body = { topic: values.topic, difficulty: values.difficulty.toLowerCase(), kind: values.kind.toLowerCase(), prompt: values.prompt,
        marking_rule: values.marking_rule.toLowerCase(), rubric: values.rubric, options: options.map(o => ({ id: o.id, label: o.label })), correct_option_ids: keys };
      const contentIssues = questionIssues(body);
      if (contentIssues.length) invalid(contentIssues);
      const existing = this.questions.find(q => q.id === id);
      if (existing && existing.owner_id !== this.me.id) invalid([{ code: "id_in_use", message: "This question ID is already in use.", field: "question_id" }]);
      if (!existing) return { key: id, keyField: "question_id", action: "created", apply: () => this.#storeQuestion(body, id) };
      const same = JSON.stringify(this.#content(existing.versions.at(-1))) === JSON.stringify(this.#normalize(body));
      return same ? { key: id, keyField: "question_id", action: "unchanged" } : { key: id, keyField: "question_id", action: "updated", apply: () => this.#revise(existing, body) };
    }, dryRun));
  }

  // ---------------------------------------------------------------- roster
  getRoster(id) { return this.#reply(() => this.#rosterOut(this.#own(this.exams, id, "Exam"))); }
  enroll(id, emails) {
    return this.#reply(() => {
      const e = this.#own(this.exams, id, "Exam");
      this.#rosterOpen(e);
      const issues = [], accounts = [];
      emails.forEach((email, i) => { const [a, issue] = this.#candidateIssue(email); if (issue) issues.push({ ...issue, row: i + 1 }); else if (!accounts.includes(a)) accounts.push(a); });
      if (issues.length || !accounts.length) invalid(issues.length ? issues : [{ code: "required", message: "Enter at least one email.", field: "candidate_email" }]);
      accounts.forEach(a => this.#admit(e, a.id));
      return this.#rosterOut(e);
    });
  }
  setEnrollment(id, candidateId, active) {
    return this.#reply(() => {
      const e = this.#own(this.exams, id, "Exam");
      this.#rosterOpen(e);
      const x = this.enrollments.find(r => r.exam_id === id && r.candidate_id === candidateId);
      if (!x) fail(404, "not_found", "Enrollment was not found.");
      x.active = active;
      return this.#rosterOut(e);
    });
  }
  importRoster(id, csvText, { dryRun = false } = {}) {
    return this.#reply(() => {
      const e = this.#own(this.exams, id, "Exam");
      this.#rosterOpen(e);
      return this.#runImport(csvText, ["candidate_email"], [], values => {
        const [a, issue] = this.#candidateIssue(values.candidate_email);
        if (issue) invalid([issue]);
        const current = this.enrollments.find(x => x.exam_id === e.id && x.candidate_id === a.id);
        return { key: a.id, keyField: "candidate_email", action: !current ? "created" : current.active ? "unchanged" : "updated", apply: () => this.#admit(e, a.id) };
      }, dryRun);
    });
  }
}
