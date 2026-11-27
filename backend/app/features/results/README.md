# Results (FastAPI)

Lane `work/results`. Requirements FR10 (monitor and announce), FR11 (grade), FR12 (review and release), SR02 (PDF reports), SR05 (question analytics) and SR06 (report verification). Acceptance cases AT06 (monitor side), AT07, AT08 and AT09.

## Layers

| Layer | Path | Responsibility |
| --- | --- | --- |
| Domain | `domain/` | `score_objective` and `score_finalized_item` (FR11), `validate_manual_award`, release gates (FR12), analytics and class summary (SR05), and verification code and digest helpers (SR06). |
| Ports | `ports.py` | Read and write repositories over the contract tables, the account directory, a `PdfRenderer`, and a unit of work that supplies database time. |
| Services | `services/` | `MonitorService`, `GradingService`, `ResultsService` and `ReportService`, bundled as `ResultsModule`. |
| Adapters | `adapters/` | `InMemoryResultsStore` for tests, SQLAlchemy over the contract schema (`sql_uow_factory`), and `ReportLabPdfRenderer`, which uses `invariant=1` so output bytes are reproducible. |
| HTTP | `api/` | `build_router(module, current_actor)`. `ResultsRoute` renders uniform errors and sets `Cache-Control: no-store`. |

## Mounting (platform maintainer)

```python
from sqlalchemy import create_engine
from backend.app.features.results import ReportLabPdfRenderer, ResultsModule, build_router, sql_uow_factory
from app.platform.identity import current_actor   # foundation-owned

results = ResultsModule(sql_uow_factory(create_engine(DATABASE_URL)), ReportLabPdfRenderer())
app.include_router(build_router(results, current_actor), prefix="/api")
```

`current_actor` must return `ports.Actor(id, roles, enabled)`, raise 401 when the session is absent or expired, and enforce CSRF on writes. `POST /reports/verify` is public; consider rate-limiting it at the edge.

**Import root.** This lane imports `backend.app.features.results` (repo root on `sys.path`). The authoring lane imports `app.features.authoring` (`backend/` on `sys.path`). The platform should settle on one root before mounting both.

**Dependencies** for `backend/pyproject.toml`: `fastapi`, `sqlalchemy>=2`, `reportlab`, plus `pypdf`, `pytest` and `httpx` for tests.

## Endpoints

| Method and path | Purpose | Access |
| --- | --- | --- |
| `GET /exams/{id}/monitor` | Status, counts, roster progress, incident timeline and announcements (server time included) | Owner |
| `GET·POST /exams/{id}/announcements` | Read or post the exam feed; posting only while published and before close | Owner posts; owner or actively enrolled candidate reads |
| `GET /exams/{id}/marking` | Finalized written responses with private rubric, cap and award | Owner |
| `PUT /attempts/{id}/items/{slot}/grade` | `awarded_marks` in [0, cap], at most 2 decimals; frozen after release | Owner |
| `GET /exams/{id}/results` | Release gate, class summary, score register and question analytics | Owner |
| `POST /exams/{id}/results/publish` | Release after close when every real attempt is final and graded; issues PDFs | Owner |
| `GET /exams/{id}/report` | Class summary PDF generated from real graded attempts | Owner |
| `GET /me/attempts/{id}/result` · `/report` | Own released score, or the exact issued PDF bytes | Candidate (404 until released) |
| `POST /reports/verify` | `{verification_code, sha256_hex}` → `{valid}` only | Public |

## Built from persona walkthroughs

Scripted persona walkthroughs drive the preview harness, count actions and record outcomes.

| Persona task | Before | After |
| --- | --- | --- |
| Verifier types the code and digest exactly as printed on the report | **Rejected** | Verified. `VerificationCode` (Crockford base-32, 140 bits, in groups of four) and `Sha256Digest` accept spaces, hyphens, case and look-alikes |
| Invigilator asks who will run out of time first | Not answerable from the monitor | "Next to finish" line, a Time left column and time left on each desk, from the server clock (IN02) |
| Examiner marks without seeing who wrote the script | Names always visible; no progress shown | Blind marking switch (scripts A, B, …; names and finish times hidden; ordered by label), progress rule and "Next unmarked" |

## Boundaries with other lanes

- **Delivery** calls `score_finalized_item(kind, rule, max_marks, selected_ids=…, correct_ids=…, written_answer=…)` inside its finalization transaction. It returns `Decimal` marks, or `None` for a nonblank written answer awaiting an examiner. The keys come from authoring's frozen paper.
- **Authoring** owns publication and the paper. Results only reads `exam`, `exam_item` and the question versions.

## Tests

```sh
pip install fastapi sqlalchemy reportlab pypdf pytest httpx
python -m pytest tests/results                     # memory and SQLite adapters
node --test tests/results/frontend/*.test.mjs      # client rules and the fixture adapter
```
