# Authoring (FastAPI)

Lane `work/authoring`. Requirements FR03 (exam configuration), FR04 (question bank), FR05 (publish a fixed paper), FR06 (eligibility), SR03 (sandbox) and SR04 (bulk import). Acceptance cases AT02, AT03, AT06 and AT10.

## Layers

| Layer | Path | Responsibility |
| --- | --- | --- |
| Domain | `domain/` | Pure objects with no framework imports. `Question` keeps an append-only list of `QuestionVersion`s. `Exam` freezes when it is published. `PublicationPolicy` holds the FR05 checklist, `EntryPolicy` the FR06 entry rule, and `FrozenPaper` the handoff to delivery. |
| Ports | `ports.py` | The repositories, the account directory (foundation identity) and a `UnitOfWork` that supplies database time. |
| Services | `services/` | Use cases. Each one checks role (403) and ownership (404), runs in one transaction and returns read models. `CsvImport` is a template method: subclasses plan rows, and the base class owns parsing, duplicates, row/field issues and the atomic commit. |
| Adapters | `adapters/` | `MemoryDatabase` serves tests and fixtures. `SqlDatabase` uses SQLAlchemy Core over the contract tables, takes `FOR UPDATE` locks and reads `clock_timestamp()`. |
| HTTP | `api/` | Pydantic request models, response presenters and `AuthoringRoute`, which renders stable error bodies and sets `Cache-Control: no-store`. |

## Mounting (platform maintainer)

```python
from sqlalchemy import create_engine
from app.features.authoring.adapters.sql import SqlDatabase
from app.features.authoring.api import build_router
from app.features.authoring.services import AuthoringModule
from app.platform.identity import argon2id_hash, current_actor   # foundation-owned

db = SqlDatabase(create_engine(DATABASE_URL), hasher=argon2id_hash)
authoring = AuthoringModule(db.unit_of_work)
app.include_router(build_router(authoring, current_actor), prefix="/api")
```

`current_actor` is the platform's session dependency. It must return `ports.Actor(id, roles)`, raise 401 when the session is absent or expired, and enforce CSRF on writes.

## Endpoints

| Method and path | Purpose | Notes |
| --- | --- | --- |
| `GET /exams` | Owned exams with state, item count, allocated marks and roster size | Examiner |
| `POST /exams` · `PUT /exams/{id}` | Create a draft or edit its particulars | 409 `exam_published` once frozen |
| `GET /exams/{id}` | Particulars, pinned slots and the publication checklist | |
| `PUT /exams/{id}/items` | Replace the slot list: `[{question_id, max_marks, version_id?}]` | An existing pin is kept unless `version_id` is given |
| `POST /exams/{id}/publish` | Validate under the exam lock, then freeze | 422 `paper_invalid` with item and field issues |
| `POST /exams/{id}/duplicate` | Copy particulars and pinned versions into a new draft (any source state) | 201; roster not copied; original untouched |
| `POST /exams/{id}/preview` | Sandbox paper in the attempt-item shape, without keys | Writes nothing |
| `GET·POST /exams/{id}/enrollments` · `PATCH …/{candidate_id}` | Roster, enroll by email, withdraw or restore | 409 `exam_closed` after close |
| `POST /exams/{id}/enrollments/import?dry_run=` | Roster CSV (`candidate_email`) | `text/csv` body, 2 MB maximum |
| `GET /questions?q=&topic=&difficulty=&kind=` | Search the bank (latest versions) | |
| `POST /questions` · `POST /questions/{id}/versions` | Create, or append a version (201; 200 when unchanged) | |
| `GET /questions/{id}` | Full history, newest first, and paper usage | |
| `POST /questions/import?dry_run=` | Question CSV in the SRS §7 columns | A known ID with changed content appends a version |
| `POST /admin/accounts/import?dry_run=` | Candidate CSV (`email`, `display_name`) | Admin only. Initial credentials are returned once. |

Errors use one shape: `{"error": {"code", "message", "issues": [{"code", "message", "field", "item", "row"}]}}`. Marks travel as fixed-point strings (`"10.00"`). Timestamps are ISO 8601 with an offset.

## Boundaries for other lanes

- **Delivery:** `authoring.exams.frozen_paper(exam_id)` returns the immutable paper, including keys, for server-side use only. `FrozenPaper.candidate_items()` is the only projection safe to show candidates. `authoring.roster.entry_decision(actor, exam_id)` applies the FR06 entry rule with database time; it returns 404 for exams the candidate may not see. `authoring.roster.assigned_exams(actor)` feeds `/me/exams`.
- **Results:** `FrozenItem.marking_rule` and `correct_option_ids` feed `score_objective`.

## Tests

```sh
pip install fastapi sqlalchemy pytest httpx
python -m pytest tests/authoring                 # every scenario on the memory and SQLite adapters
node --test tests/authoring/frontend/*.test.mjs  # client rules and the fixture adapter
```
