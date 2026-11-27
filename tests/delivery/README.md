# Candidate delivery handoff

The candidate pages and API implement FR07–FR09, IN01–IN02, SR01, SR07 and SR08. This checkout carries the `work/delivery` reservation on `feature/candidate-workspace`.

## Platform integration

- Mount `CandidateExams` at `/me/exams` and `CandidateAttempt` at `/attempts/:id` inside the authenticated Folio shell. Pass the signed-in account UUID as the string `accountId` and the route UUID as `attemptId`. The list accepts an optional `navigate(path)` callback. The browser uses same-origin JSON requests and the session cookie. Route document navigations to the shell and JSON requests to FastAPI. Authoring can render `AttemptView` with its transient controller and `preview` flag.
- In the root-scoped module service worker, call `installDeliveryShell(self, { version, shell, assets })` with a build-specific version, a public, identity-free HTML shell, and the complete public asset manifest. The platform must restore the current account context on offline reload. Await `purgeDeliveryAccount(accountId)` on logout before switching accounts. The attempt record, drafts and scratchpad are scoped by account and attempt.
- Mount `create_router(connect, session_account_id, score_objective)` from `backend.app.features.delivery.router`. Supply a fresh psycopg connection context with dictionary rows, default READ COMMITTED isolation, and commit on successful exit. Use the platform's revocable session dependency, returning a UUID. Apply the repository schema first. The results scorer receives kind, selected and correct ID sets, marking rule and Decimal cap.
- Enter `expiry_worker(connect, score_objective)` from `backend.app.features.delivery.worker` in the application's lifespan. The worker runs immediately on startup and then every five seconds. Row locking supports multiple workers. Save and submit enforce the cutoff even between sweeps.

## Verification

Run from the repository root with Python, FastAPI, psycopg 3, the FastAPI test client dependencies, Node, React, Vite and Playwright available.

| Case | Command | Coverage |
| --- | --- | --- |
| AT03, AT04, AT05, AT11 | `python -m unittest discover -s tests/delivery -v` | Set `DELIVERY_TEST_DSN` to a disposable PostgreSQL database. Each test creates and removes a unique schema. Tests exercise the FastAPI router with the real schema, controlled clock, session fixture and deterministic scorer. |
| AT04 | `node --test tests/delivery/queue.test.mjs` | Chained edits, independent stale revisions and both conflict choices. |
| AT04, AT11 | `node --test tests/delivery/browser.test.mjs` | Builds the real pages, serves a fixture API on loopback and drives Chromium through offline navigation, editing, recovery, submission and logout. Set `CHROME_PATH` to use installed Chrome and `DELIVERY_SCREENSHOTS` to capture desktop and 360 px screenshots. |

The protected scope checker selects its lane by branch name. A maintainer needs to register the requested branch as an alias of `work/delivery` for the PR check.
