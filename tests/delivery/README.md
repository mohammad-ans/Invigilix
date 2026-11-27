# Candidate delivery handoff

The candidate pages and API implement FR07–FR09, IN01–IN02, SR01, SR07 and SR08. This checkout carries the `work/delivery` reservation on `feature/candidate-workspace`.

## Competition demo

[Watch the candidate journey](media/candidate-demo.mp4). A candidate answers a question, reloads a written draft offline and reconnects after a second device changes the answer. The film follows the choice of draft through review and the server-issued receipt. It uses the React pages, FastAPI router and PostgreSQL with fictional exam data and a test session.

Scroll through the register to move the exam counter and the calendar marker together. The engraved opening ticket turns as it leaves the page, and each review row inks its margin as it enters. Jump directly to a section with the keyboard. Reduced motion keeps the same navigation and date tracking with immediate, static updates.

## Platform integration

- Mount `CandidateExams` at `/me/exams` and `CandidateAttempt` at `/attempts/:id` inside the authenticated Folio shell. Pass the signed-in account UUID as the string `accountId` and the route UUID as `attemptId`. The list accepts an optional `navigate(path)` callback. The browser uses same-origin JSON requests and the session cookie. Route document navigations to the shell and JSON requests to FastAPI. Authoring can render `AttemptView` with its transient controller and `preview` flag.
- In the root-scoped module service worker, call `installDeliveryShell(self, { version, shell, assets })` with a build-specific version, a public, identity-free HTML shell, and the complete public asset manifest. The platform must restore the current account context on offline reload. Await `purgeDeliveryAccount(accountId)` on logout before switching accounts. The attempt record, drafts and scratchpad are scoped by account and attempt.
- Mount `create_router(connect, session_account_id, score_objective)` from `backend.app.features.delivery.router`. Supply a fresh psycopg connection context with dictionary rows, default READ COMMITTED isolation, and commit on successful exit. Use the platform's revocable session dependency, returning a UUID. Apply the repository schema first. Import `score_objective` from `backend.app.features.results.domain.grading` on the integrated branch.
- Enter `expiry_worker(connect, score_objective)` from `backend.app.features.delivery.worker` in the application's lifespan. The worker runs immediately on startup and then every five seconds. Row locking supports multiple workers. Save and submit enforce the cutoff even between sweeps.

## Verification

Run from the repository root. The Python tests use FastAPI, psycopg 3, and the FastAPI test client dependencies. The browser tests resolve React 19, React DOM 19, Vite 7 and Playwright from the repository root. In a fresh checkout, `npm install --no-save --package-lock=false react@19 react-dom@19 vite@7 playwright` supplies those test dependencies. Use `npx playwright install chromium` or set `CHROME_PATH` to a local Chromium executable.

| Case | Command | Coverage |
| --- | --- | --- |
| AT03, AT04, AT05, AT11 | `python -m unittest discover -s tests/delivery -v` | Set `DELIVERY_TEST_DSN` to a disposable native PostgreSQL database. Each case creates and removes a unique schema. The cutoff case waits for PostgreSQL to report that a save and a submission are both blocked before advancing the clock. |
| AT03, AT04, AT05 | `DELIVERY_LIVE_BROWSER=1 python -m unittest discover -s tests/delivery -v` | With the same DSN and Uvicorn installed, this also builds the pages and starts FastAPI on loopback. Chromium recovers a lost acknowledgment, reloads offline, resolves a conflicting edit from a second device, checks access as another candidate and reopens the receipt. The test checks persisted revisions, marks and events in PostgreSQL. The shell, login cookies and scorer are test fixtures. |
| AT04 | `node --test tests/delivery/queue.test.mjs tests/delivery/session.test.mjs` | Offline edit compaction, revision chains, access denial, explicit saved-only submission, shuffled receipt numbering and wall-clock changes. |
| AT04, AT11 | `node --test tests/delivery/browser.test.mjs` | Builds the real pages, serves a fixture API on loopback and drives Chromium through offline navigation, editing, recovery, submission and logout. Set `CHROME_PATH` to use installed Chrome and `DELIVERY_SCREENSHOTS` to capture desktop and 360 px screenshots. |

The scope checker accepts the local branch name `work/delivery`. A PR opened from a remote branch named `work/delivery` uses that reservation directly. A PR opened from the previous remote name `feature/candidate-workspace` would need a maintainer-approved alias.

## Candidate save rehearsal

With the disposable PostgreSQL DSN set, run `PYTHONPATH=. python tests/delivery/rehearse_saves.py`. Fifty test accounts each save one written response over HTTP every five seconds for ten minutes. The harness checks every acknowledged revision, starts a fresh FastAPI process and reads every final response back as its owner.

The November 27 local loopback run acknowledged 6,000 of 6,000 saves in 600.1 seconds. The 95th-percentile response was 139.9 ms against the 2-second SRS target. All 50 accounts recovered revision 120 and the expected answer after the restart. Deployment latency, shared authentication and examiner feed freshness belong to the full three-role rehearsal.
