# Software Requirements Specification

## Secure Examination Management System

Version 1.0   •   27 November 2026   •   Web-e-Thon / Technoverse 5.0

This specification defines how an institution conducts a timed exam from enrollment to result publication. It gives the React and FastAPI team the behavior to implement, the records to persist, and acceptance cases that a tester can run with fictional candidates.

### 1  Scope and users

The product covers all eight core areas and all eight secondary features in the competition brief. The selected innovation is failure-resilient examinations (§5.3). A disconnected candidate can continue on the same device. Only answers accepted by the server before the deadline contribute to the result.

| Actor | Permitted work |
| --- | --- |
| Administrator | Manage accounts and role assignments, disable access, and import candidate accounts. An administrative role alone grants no access to answers or grades. |
| Examiner | Manage owned exams, question versions and rosters. Preview, monitor, announce, grade, review results and publish for those exams. |
| Candidate | View assigned exams, take an eligible exam, submit or resume an attempt, and obtain their own released result and report. |
| Report verifier | Present a report code and file digest. Receive a validity result with no candidate, exam or score details. |

### Product policies

The proposed baseline gives each exam one owning examiner and each enrollment one real attempt. The scheduled close caps the time for late starters. Results release for the whole exam after it closes and all real attempts are final and graded. Accounts may hold multiple roles.

### Reading the specification

“Shall” defines a requirement of this baseline. FR identifies core behavior, SR secondary features, IN the innovation, NFR quality requirements and DEL delivery. AT identifies an acceptance case. Numerical performance targets are proposed engineering targets. Competition obligations are attributed to the brief.

Sections 2–3 define storage and object responsibilities. Sections 4–6 cover the workflow and features. Sections 7–8 define interfaces, quality and delivery. Sections 9–10 link requirements to acceptance tests.

## 2  Storage choices by data structure

Use PostgreSQL as the authoritative server database. Use IndexedDB for work that must survive a refresh on one device. The same answer can exist in both places while its local revision is waiting for acknowledgment.

| Data and access pattern | Chosen store | Reason and lifetime |
| --- | --- | --- |
| Accounts, roles, rosters, exams and bank revisions | PostgreSQL tables | Foreign keys link identities, ownership and assignments. Persist the published version of each question for historical review. |
| Attempt, ordered items, selections and awards | PostgreSQL tables | A save can touch several choices. Commit the full item update and revision together. Keep accepted work and final awards across sessions and devices. |
| Chronological incidents and announcements | PostgreSQL event and message rows | Index by attempt or exam and time. The examiner can query a timeline without a separate logging database. |
| Scores, aggregates and item statistics | SQL view and grouped queries | Derive totals from awards and rates from real finalized attempts. A missing award leaves the final total pending. |
| Issued PDF and verification record | PostgreSQL BYTEA and metadata | Keep the exact issued bytes, code, digest and attempt together. Generate examiner class summaries on demand from authorized data. |
| Unsynced edits, current paper and scratchpad | IndexedDB in the browser | Key by signed-in account and attempt, and by slot where applicable. Restore on the same device. Purge on logout or confirmed finalization. |
| App shell, preview and import staging | Browser Cache API for static assets. Memory for preview and file parsing. | Cached static assets enable offline refresh. Sandbox answers expire when preview ends. Validate imports in memory before committing one database transaction. |

### When an answer becomes authoritative

React may show “On this device” once IndexedDB commits the edit. FastAPI returns the accepted revision after the PostgreSQL transaction commits. Only then may the UI show “Saved on server”. A new device restores acknowledged revisions after login. If local storage fails, the UI shall report that recovery of unsaved edits is unavailable.

Storage references   PostgreSQL constraints   ·   PostgreSQL binary data   ·   IndexedDB   ·   Cache API

## 3  Domain objects and relational schema

The companion exam_schema.sql defines 15 tables and one view. Objects own business decisions in FastAPI. SQL constraints protect record identity and relationships across every write.

| Object and behavior | Tables or view | Relationship or invariant |
| --- | --- | --- |
| Account and AccessPolicy authorize | account, account_role, login_session | One account may have many roles and sessions. Email is unique after trimming and case normalization. Store hashes for passwords and session tokens. |
| Question versions its content | question, question_version, question_option | One question has many immutable versions. Each option belongs to exactly one version. The private key, type and marking rule are versioned. |
| Exam publishes a paper | exam, exam_item, enrollment | Exam and candidate have a many-to-many relationship through enrollment. Each (exam_id, slot) pins one question version and a positive mark cap. |
| Attempt saves and closes | attempt, attempt_item, attempt_option | An enrollment has zero or one real attempt. Each assigned slot has one response and a stable display position. A composite foreign key restricts each choice to its assigned revision. |
| Monitoring records context | attempt_event, announcement | One attempt has many timestamped events. One exam has many examiner announcements, readable by its eligible candidates. |
| GradingPolicy scores and ResultPublication releases | attempt_item, attempt_score (view), result_report | A nullable item award distinguishes pending from zero. Each attempt has at most one issued candidate report. The exam owns the release timestamp. |

### Types and query paths

Use UUIDs for entity identifiers, TIMESTAMPTZ for server instants, NUMERIC(8,2) for marks, TEXT for written work, and ordered integer positions for slots and choices. Monitor due attempts through the open-attempt deadline index. List a candidate’s exams through the enrollment index. Index each event timeline by parent and recorded time.

### Transaction ownership

Publish validates the full paper under an exam lock. Start locks the exam in shared mode and then the enrollment. Save, submit and expiry lock the attempt before reading database time. Manual grading and release lock the exam first. Check role, ownership, cross-row mark caps and immutable publication state in the service transaction.

## 4  Access and exam preparation

The examiner prepares and publishes a paper before an eligible candidate can start it. These requirements trace to §§3.1–3.4 of the problem statement.

FR01   Authenticate.  The system shall sign in enabled accounts, establish a revocable session and show actions appropriate to their assigned roles. Logout, expiry or account disablement shall prevent further protected actions.

FR02   Authorize records.  Administrators shall create and update accounts and assign or revoke roles. FastAPI shall check the current role and record scope for each read or write. An examiner may access owned exams and bank items. A candidate may access their own assigned exams, attempts and released results.

FR03   Configure an exam.  An examiner shall create, edit and review a draft with title, instructions, opening and closing times, duration, total marks and shuffle settings. Require a positive duration, a positive total and a close later than the opening.

FR04   Manage the bank.  An examiner shall create, find by topic or difficulty, edit and assign single-answer, multiple-select and written questions. An edit appends a version with the prompt, options, key, marking rule and optional rubric. Existing assignments retain their version.

FR05   Publish a fixed paper.  The examiner shall review the draft and publish only a nonempty paper with valid keys, distinct bank questions and positive item caps summing to the declared total. Objective items need at least two options. Single-answer items need exactly one key, multiple-select items at least one, and written items no options. Publication freezes slots, versions, caps, schedule and settings. Candidate paper responses shall omit keys and rubrics.

FR06   Manage eligibility.  The examiner shall enroll eligible candidate accounts and review the roster. Candidates shall see instructions and the status of assigned published exams, including upcoming, available and completed. Entry requires an active account, candidate role, active enrollment and an open exam window.

### State and visibility

| Exam state | Candidate experience |
| --- | --- |
| Draft | The owner can edit and preview. The candidate has no access. |
| Published before opening | An enrolled candidate can see metadata and instructions. Questions are withheld. |
| Ongoing | Opening time ≤ database time < closing time. An eligible candidate can start or resume a live attempt. A finalized attempt shows a receipt. |
| Completed | The window has closed. Entry is closed. The candidate can see a result only after the examiner releases it. |

## 5  Exam delivery and evaluation

The attempt is the unit of timing, saving and submission. These requirements cover §§3.5–3.8 and the selected innovation in §5.3.

FR07   Start or resume.  The server shall create the attempt, assigned items and applicable shuffled orders atomically. A repeated start shall return the existing authorized attempt. Fix the deadline at the earlier of start plus duration and the scheduled close. Restore the original order, acknowledged answers and deadline on return.

FR08   Work and review.  The workspace shall show prompts, available marks, remaining time, navigation and answered, unanswered and flagged states. Candidates shall edit, clear, flag, autosave and review answers before submitting. Written answers use text. Objective answers use stable option IDs.

FR09   Finalize once.  Submit and expiry shall share one terminal transition. On submit, show pending edits and try to flush them. At or after the deadline, finalize only accepted answers, even with the browser closed. Periodically close due attempts and check again on access. Duplicate requests return the same receipt.

FR10   Monitor and announce.  The owning examiner shall see exam status, active attempts, answered counts and dated incidents. They may post announcements during the exam. Enrolled candidates shall receive them in the workspace. Incident indicators are observations for human review and carry no automatic penalty.

FR11   Grade responses.  At finalization, score single-answer items by exact match. For multiple-select, support exact set or partial credit with no wrong selection. For the latter, award cap × selected correct / total correct, or zero if any wrong choice is selected. Blank responses earn zero. A nonblank written answer awaits an examiner award from zero through the cap. Round each award to two decimal places and sum.

FR12   Review and release.  The owner shall review candidate scores and exam summaries from real submissions. Release only after the exam closes and all real attempts are final and fully graded. Freeze released awards. Candidates shall see only their own released results. Keep completed records available for authorized review.

### Recovery during an interruption

IN01   Recover pending work.  Persist local full-item edits and their base revisions. On reconnect, replay them in order per item. A lost acknowledgment shall resolve to the accepted revision when the content matches. A conflicting stale edit shall preserve the local draft and offer a choice before expiry.

IN02   Keep the cutoff fair.  After acquiring the attempt lock, evaluate database time before accepting a write. At the cutoff return the receipt and identify any unaccepted local edits. On a replacement device, restore server-accepted work and the original deadline. A client timestamp shall never extend either deadline or eligibility.

## 6  Secondary features

All eight features in §4 are part of the acceptance baseline. Each requirement identifies the user action and an observable outcome.

SR01   Network status.  Show saving, saved on server, on this device and save failed states. Detect failed requests as well as loss of connectivity. An unstable connection shall never cause a queued edit to appear acknowledged.

SR02   PDF reports.  Generate a readable class summary for the owning examiner using real performance data and a downloadable personal report for a candidate after release. The displayed and exported score, denominator and exam identity shall agree.

SR03   Exam sandbox.  The examiner shall preview an owned paper in the candidate workspace and complete a simulated submission. Use transient state. Real attempt counts, grades, incidents, issued reports and analytics shall be identical before and after preview.

SR04   Bulk import.  Administrators shall import candidate accounts and examiners shall import bank questions and roster entries from UTF-8 CSV. Validate the header, required fields, references, role scope, duplicates and question keys. On failure identify the row and field. Commit a valid file atomically.

SR05   Question analytics.  For each assigned question version show finalized exposure count, skipped count and rate, common incorrect selections and observed facility. For each graded exposure divide awarded marks by that item’s cap, then average those fractions. Display denominators and “No data” for an empty group.

SR06   Report verification.  Assign the issued candidate PDF a random code with at least 128 bits of entropy. Embed the code, hash the final bytes using SHA-256 and persist both the bytes and digest. The public verifier shall return a validity result for the code and digest without disclosing identity, score or PDF contents.

SR07   Workspace preferences.  Candidates shall choose standard or focus layout and a font size from 80% to 200%. Save preferences on the account and restore them after sign-in on another device. Both layouts shall retain timer, save feedback and navigation.

SR08   Scratchpad.  Provide a dedicated rough-work area within each real attempt. Restore it after a same-device refresh, isolate it by account and attempt, and clear it at logout or confirmed closure. Exclude rough work from submissions, grades and reports.

### How secondary features fit the workflow

The examiner previews and imports while preparing an exam, then inspects question performance after submissions. The candidate uses the scratchpad, save status and layout preferences while working. Issued reports remain byte-for-byte reproducible on subsequent downloads.

## 7  External interfaces

React uses a same-origin HTTPS JSON API implemented in FastAPI. The database is private to the backend. The browser exchanges stable option identifiers and full-item revisions when saving.

| Interface | Contract and observable result |
| --- | --- |
| Accounts and preferences | POST /sessions signs in. PATCH /admin/accounts/{id} updates access. PATCH /me/preferences saves the signed-in user’s font size and layout. |
| Authoring and roster | POST /exams creates a draft. POST /questions/{id}/versions adds a revision. POST /exams/{id}/enrollments adds candidates. The exam’s /preview and /publish endpoints preview and publish its fixed paper. |
| Entry and workspace | GET /me/exams lists eligible records. POST /exams/{id}/attempts starts or resumes. GET /attempts/{id} returns server time, deadline, ordered candidate-safe paper, accepted answers and revisions. |
| Saving and submission | PUT /attempts/{id}/items/{slot} accepts base_revision, flagged, and either selected_option_ids or written_answer. Return the accepted revision and saved_at. POST /attempts/{id}/submit returns attempt ID, close reason and finalization time. |
| Monitoring and release | GET /exams/{id}/monitor lists scoped progress. POST or GET /exams/{id}/announcements writes or reads the exam feed. PUT /attempts/{id}/items/{slot}/grade records an award. POST /exams/{id}/results/publish releases reviewed results. |
| Results and reports | GET /me/attempts/{id}/result or /report returns an own released score or PDF. GET /exams/{id}/report returns an owner-only class PDF. POST /reports/verify accepts verification_code and sha256_hex and returns valid as a boolean. |

### Validation and error responses

Exchange timestamps as ISO 8601 instants with an explicit offset. Return 401 for an absent or expired session, 403 for a disallowed role, and 404 for inaccessible private records. Return 409 for a stale revision, closed attempt or invalid state transition, and 422 for invalid input. Use stable error codes and field or row details. A conflict response includes only the actor’s authorized current state.

### CSV inputs

Candidate rows require email and display_name. Generate each initial credential securely and expose it once to the importing administrator. Enrollment rows use candidate_email within the selected exam. Question rows require question_id (UUID), topic, difficulty, kind, prompt and marking_rule. Objective rows also require options and correct_option_ids, encoded as JSON arrays within quoted CSV fields. Each option carries a positive integer ID and label. Written rows use empty arrays and may supply a rubric.

## 8  Quality and delivery requirements

The competition sets technical and delivery constraints in §§6–8. The workload, latency and viewport values below are proposed acceptance targets for the team’s deployment.

NFR01   Security and privacy.  Use HTTPS, salted Argon2id password hashes, secure HttpOnly same-site session cookies, CSRF checks for cookie-authenticated writes and server-side authorization. Exclude credentials, tokens, private keys, answer payloads and report bytes from logs. Candidate APIs, error bodies and caches shall omit marking keys and rubrics.

NFR02   Atomicity and durability.  An acknowledged save shall survive an application restart. A race among save, submit and expiry shall yield one receipt and a consistent set of item awards. A failure within start, close, grade or import shall roll back every dependent write in that transaction.

NFR03   Accessibility and layout.  At a 360 CSS-pixel viewport, users shall be able to read, answer, flag, navigate and submit without horizontal scrolling. All essential actions shall be keyboard-operable with visible focus and labeled controls. Save and timer warnings shall have text equivalents and be announced accessibly.

NFR04   Response and freshness.  Exercise the demonstration deployment with 50 active candidates, each saving one item every 5 seconds for 10 minutes. Target a 95th-percentile save response of at most 2 seconds, no lost acknowledgments and monitor or announcement updates visible within 10 seconds on a healthy connection.

NFR05   Maintainability.  Keep UI, request validation, domain policies and SQL access separate. Use SQLAlchemy and repeatable Alembic migrations. Expose a FastAPI OpenAPI contract. Validate input in React and FastAPI, and recreate the schema and fictional seed data from the documented setup.

NFR06   Operating constraints.  The full workflow shall run with a browser, FastAPI, PostgreSQL and standard local libraries. No required feature may depend on paid APIs, billing-enabled external services, proprietary datasets or specialized hardware.

### Competition delivery

DEL01   Submission and demonstration.  Provide a deployed functional application and a Git repository with version history. The README shall include setup steps, dependencies, test logins for each role and the implemented innovation. Use fictional data for the 15-minute live evaluation. Follow the official guide’s deadline for commits, pushes, builds and deployments and preserve genuine timestamps.

The brief allocates 10 development hours for 1–3 participants. Evaluation weights are core functionality 30, secondary features 15, technical quality and reliability 20, innovation 15, and UI/UX 20.

## 9  Acceptance tests for the exam lifecycle

These are planned acceptance tests. Use an admin, two examiners and two candidates. Give each examiner a separate exam. Enroll only one candidate in the timed exam unless a case needs both.

AT01   Authentication and scope     FR01 · FR02 · NFR01

Sign in as each role. Change a role, disable an account, log out, and request another user’s attempt or exam. Inspect candidate responses and logs. Pass when protected calls reflect the current permissions, refused calls reveal no records, session cookies have the specified flags, and private keys and credentials are absent from returned or logged data.

AT02   Publish and preserve a paper     FR03 · FR04 · FR05

Create three bank items worth 2, 4 and 4. Try a mismatched declared total and a single-answer key with two correct options. Fix both, publish, then edit a bank prompt and key. Pass when invalid drafts cannot publish. The published 10-mark paper retains the original revision, order rules and private key.

AT03   Entry and resumption     FR06 · FR07

Use a 10:30–11:00 window, a 30-minute duration and shuffling. Try early entry and unenrolled entry, then start twice at 10:42 and refresh. Pass when only the enrolled candidate starts. Both starts return the same attempt, question/choice order and 11:00 deadline. The roster and dashboard show the correct access status.

AT04   Reconnect and resolve a conflict     FR08 · IN01 · IN02 · SR01

At 10:56 acknowledge revision 4. Disconnect, edit and flag, refresh offline, then reconnect at 10:59. Repeat with a lost acknowledgment and with a different revision saved by a second tab. Pass when local and server states are labeled accurately. An accepted update is applied once. A stale conflicting edit requires a choice and never overwrites a newer answer silently.

AT05   Expiry and duplicate submission     FR09 · IN02 · NFR02

Leave one edit local, reconnect at exactly 11:00 and submit twice. Repeat with two simultaneous requests just before cutoff and with the expiry worker restarted. Pass when at cutoff only committed, timely accepted work counts. There is one terminal state, one set of awards and one receipt. A fresh device restores the server record and the deadline.

AT06   Preview and monitor     FR10 · SR03

Preview and submit a sandbox exam, then start a real attempt. Save one answer, reconnect, and post an announcement as the owning examiner. Pass when preview changes no real counts. The monitor shows real progress and incident context, the candidate sees the announcement, and the incident has no scoring effect.

## 10  Acceptance tests for results and operations

Use the same seeded paper for scoring and reporting. Carry its actual scores through the examiner dashboard, candidate view, exports and verification service.

AT07   Grade and publish     FR11 · FR12

Answer the 2-mark single correctly, choose {A} for a 4-mark partial-credit item keyed {A,C}, and enter written text. Try to release early and to award 5/4. Then award 3/4 and release after close. Pass when early release and invalid grades fail. The final score is 7/10. A wrong extra selection or an incomplete exact-set response earns zero. Only the candidate’s own released result is visible.

AT08   Analytics denominators     FR12 · SR05

Use two finalized exposures of one 4-mark version, one blank and one full-credit. Add a no-show and a sandbox preview. Pass when the skip rate is 1/2, observed facility is 0.50, and class summaries use real graded attempts. Zero exposures display “No data”.

AT09   PDF access and authenticity     SR02 · SR06

Download the class summary as its owner and the released personal PDF as its candidate. Verify the original and a modified copy with the same code. Repeat download. Pass when scores match the UI, the original verifies, the altered bytes fail, and repeat download returns the issued bytes. The public response contains only validity.

AT10   Bulk import     SR04 · NFR02

Import candidates, questions and enrollments. Include one invalid row among valid rows, then correct and rerun. Repeat a file with existing email or question IDs. Pass when errors identify row and field, invalid files leave zero changes, and valid files create exactly the expected records. Duplicate input creates no duplicate records.

AT11   Accessible workspace and local isolation     SR07 · SR08 · NFR03

Use keyboard-only navigation at 360 CSS pixels. Change layout and font, enter scratch text, refresh, sign in on another device and log out. Pass when controls and feedback stay accessible. Preferences follow the account, scratch text stays local, and logout removes private local data.

AT12   Rebuild and deployment rehearsal     NFR02 · NFR04 · NFR05 · NFR06 · DEL01

Rebuild from the README, inspect the API contract and migrations, run the specified load, and restart FastAPI after accepted saves. Exercise all three roles on the deployed app using only permitted dependencies. Pass when the documented setup works, all acknowledged revisions survive, measured latency and freshness meet their targets, and the repository and 15-minute demonstration cover the required delivery items.

Sources include the Technoverse 5.0 Web-e-Thon Problem Statement, §§1–8, and the companion exam_schema.sql and exam_system_design.pdf. Acceptance outcomes describe intended behavior.
