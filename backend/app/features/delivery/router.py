"""Mount create_router with a transaction context factory, session dependency and scorer."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from . import service


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flagged: StrictBool
    base_revision: StrictInt = Field(ge=0)
    selected_option_ids: list[StrictInt] | None = None
    written_answer: StrictStr | None = None


class Preferences(BaseModel):
    font_percent: StrictInt = Field(ge=80, le=200)
    workspace_layout: Literal["standard", "focus"]


def create_router(connect, session_account_id, score_objective):
    router = APIRouter()

    @router.get("/me/exams")
    def dashboard(account_id: UUID = Depends(session_account_id)):
        with connect() as db:
            return service.exams(db, account_id)

    @router.post("/exams/{exam_id}/attempts")
    def enter(exam_id: UUID, account_id: UUID = Depends(session_account_id)):
        with connect() as db:
            return service.start(db, account_id, exam_id, score_objective)

    @router.get("/attempts/{attempt_id}")
    def load(attempt_id: UUID, account_id: UUID = Depends(session_account_id)):
        with connect() as db:
            return service.paper(db, account_id, attempt_id, score_objective)

    @router.put("/attempts/{attempt_id}/items/{slot}")
    def save(attempt_id: UUID, slot: int, edit: Edit, account_id: UUID = Depends(session_account_id)):
        with connect() as db:
            status, body = service.save(db, account_id, attempt_id, slot, edit, score_objective)
        return JSONResponse(jsonable_encoder(body), status_code=status)

    @router.post("/attempts/{attempt_id}/submit")
    def submit(attempt_id: UUID, account_id: UUID = Depends(session_account_id)):
        with connect() as db:
            attempt, _, instant = service.lock_owned(db, account_id, attempt_id)
            return service.finish(db, attempt, instant, score_objective, submit=True)

    @router.patch("/me/preferences")
    def preferences(prefs: Preferences, account_id: UUID = Depends(session_account_id)):
        with connect() as db:
            # Acquire an exclusive lock before checking eligibility to serialize concurrent changes.
            db.execute("SELECT id FROM account WHERE id=%s FOR UPDATE", (account_id,))
            service.candidate(db, account_id)
            db.execute("UPDATE account SET font_percent=%s,workspace_layout=%s WHERE id=%s",
                       (prefs.font_percent, prefs.workspace_layout, account_id))
        return prefs

    return router
