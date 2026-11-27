# Deploy the examination office

The React application runs on Vercel. A continuously running FastAPI service hosts the API and checks PostgreSQL for expired attempts every five seconds, including when all browsers are closed. Both services deploy from the same repository revision.

| Service | Variable | Value |
| --- | --- | --- |
| Vercel frontend | `API_ORIGIN` | The public HTTPS origin of the FastAPI service, e.g. `https://exam-api.example.org`. Supply the origin alone. |
| FastAPI | `PUBLIC_ORIGIN` | The exact HTTPS origin where users open Folio, e.g. `https://exams.example.org`. This is the allowed browser origin for writes. |
| FastAPI and migration job | `DATABASE_URL` | The PostgreSQL connection URI supplied by your database host. Use the provider's TLS parameters. |

1. On Railway, add PostgreSQL and connect the API service to the GitHub branch containing this integration. Use the repository root as the service root. In the API service settings, set **Railway Config File** to `/tools/railway/railway.toml`. The Docker build includes both the backend and its SQL contract. [Railway configuration](https://docs.railway.com/config-as-code)
2. Set `DATABASE_URL` and `PUBLIC_ORIGIN` on the API service. For the competition demo, also set the three password variables listed below. Railway runs `python -m backend.migrations.predeploy` before starting the API. It applies pending Alembic revisions and then seeds any missing demo accounts when configured. For a deployment with demo passwords omitted, create the first administrator once with `python -m backend.app.platform.bootstrap` in the service terminal. [Railway pre-deploy commands](https://docs.railway.com/deployments/pre-deploy-command)
3. Generate the API service's public HTTPS domain. The container starts Uvicorn on Railway's assigned port. Railway checks `GET /api/health` and the service reports ready when PostgreSQL can read the account table. OpenAPI is at `/api/docs`. [Railway health checks](https://docs.railway.com/deployments/healthchecks)
4. In Vercel, select the integration branch or a branch that contains it. Set **Root Directory** to `frontend`, **Framework Preset** to **Other**, **Install Command** to `npm ci`, and **Build Command** to `npm run build`. Leave the output directory override unset. Set `API_ORIGIN` and redeploy. The build emits the static files and same-origin API proxy routes in `.vercel/output` using the [Vercel Build Output API](https://vercel.com/docs/build-output-api).
5. Open the Vercel URL, sign in as the administrator, and create an examiner and a candidate under **Accounts**. As the examiner, add a bank question, create an exam in **Exam register**, assign its marks, publish, and enroll the candidate in **Roster**. The candidate starts it from **My exams**. After submission, grade written answers in **Marking**. Once the scheduled window closes, release in **Results**. The candidate can then open **My results** and download their report.

A preview deployment that needs live writes should use its own stable frontend origin, backend configuration and test database. Build again after changing the API origin. The browser only communicates with its own site. PostgreSQL credentials belong on the backend.

## Test accounts

Set all three variables on the Railway API service to enable seeding. Each initial password accepts 12–256 characters.

| Sign-in email | Role | Initial password variable |
| --- | --- | --- |
| `demo-admin@example.test` | Administrator | `FOLIO_SEED_ADMIN_PASSWORD` |
| `demo-examiner@example.test` | Examiner | `FOLIO_SEED_EXAMINER_PASSWORD` |
| `demo-candidate@example.test` | Candidate | `FOLIO_SEED_CANDIDATE_PASSWORD` |

The seed creates the missing accounts together and stores Argon2id hashes. Existing email addresses keep their current credentials, roles, and enabled status on redeploy. Removing the variables skips future seeding. To retire an existing demo login, disable it in the account register.

## Local rehearsal

From the repository root, with Python 3.12, Node 22.12+ and a local PostgreSQL database:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e 'backend[test]'
export DATABASE_URL='postgresql://localhost/folio'
export PUBLIC_ORIGIN='http://localhost:5173'
python -m backend.app.platform.migrate
python -m backend.app.platform.bootstrap
python -m uvicorn backend.app.main:create_app --factory --port 8000
```

To rehearse the Railway pre-deploy step locally, export the three test-account passwords and run `python -m backend.migrations.predeploy` in place of the separate migration and bootstrap commands.

In a second terminal run `npm --prefix frontend ci` and `npm --prefix frontend run dev -- --host localhost --port 5173 --strictPort`. Open `http://localhost:5173`. To rehearse the built application including the offline worker, run `npm --prefix frontend run build`, then `npm --prefix frontend run preview -- --host localhost --port 5173 --strictPort` in place of the dev server.

Run the lifecycle regression with `FOLIO_TEST_DSN='postgresql://localhost/folio_test' python -m pytest -q tests/integration`. The database must exist and the test user must be allowed to create schemas. The test creates and removes only its own randomly named schema.

## Production screens from the local rehearsal

[Sign-in screen](screens/sign-in.png) · [Released candidate score](screens/released-score.png). The screenshots use disposable test accounts and records.
