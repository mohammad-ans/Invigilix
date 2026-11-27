"""FastAPI routes for authoring. The platform mounts the router returned by
:func:`build_router` and supplies ``current_actor``, its session dependency that
raises 401 for an absent or expired session and enforces CSRF on writes.

Annotations stay evaluated (no ``from __future__ import annotations``) because
FastAPI must resolve the closure-local ``Me`` dependency alias at decoration time."""
from typing import Annotated, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool

from ..domain import Difficulty, Issue, QuestionContent, QuestionKind, ValidationFailed
from ..ports import Actor, BankQuery
from ..services import AuthoringModule, CsvImport, SlotRequest
from .errors import AuthoringRoute
from .schemas import (
    EnrollIn, EnrollmentPatch, ExamDetailsIn, ExamOut, ExamSummaryOut, ImportReportOut, PaperIn,
    QuestionDetailOut, QuestionIn, QuestionOut, RevisionOut, RosterOut, SandboxOut,
)

MAX_CSV_BYTES = 2 * 1024 * 1024


def _content(body: QuestionIn) -> QuestionContent:
    unknown = body.unknown_keys()
    if unknown:
        raise ValidationFailed([Issue("unknown_key", f"Keys {unknown} match no option ID.",
                                      field="correct_option_ids")])
    return body.to_domain()


async def _csv(request: Request) -> bytes:
    data = await request.body()
    if len(data) > MAX_CSV_BYTES:
        raise ValidationFailed([Issue("file_too_large", "Upload at most 2 MB per file.",
                                      field="file")], code="import_invalid")
    return data


def build_router(module: AuthoringModule, current_actor: Callable[..., Actor]) -> APIRouter:
    router = APIRouter(route_class=AuthoringRoute, tags=["authoring"])
    Me = Annotated[Actor, Depends(current_actor)]

    async def run_import(importer: CsvImport, actor: Actor, request: Request, dry_run: bool,
                         **scope) -> ImportReportOut:
        data = await _csv(request)
        report = await run_in_threadpool(importer.run, actor, data, commit=not dry_run, **scope)
        return ImportReportOut.of(report)

    # -- exams (FR03, FR05) -----------------------------------------------------
    @router.get("/exams", response_model=list[ExamSummaryOut])
    def list_exams(actor: Me):
        return [ExamSummaryOut.of(s) for s in module.exams.list_owned(actor)]

    @router.post("/exams", response_model=ExamOut, status_code=201)
    def create_exam(body: ExamDetailsIn, actor: Me):
        return ExamOut.of(module.exams.create_draft(actor, body.to_domain()))

    @router.get("/exams/{exam_id}", response_model=ExamOut)
    def get_exam(exam_id: UUID, actor: Me):
        return ExamOut.of(module.exams.overview(actor, exam_id))

    @router.put("/exams/{exam_id}", response_model=ExamOut)
    def update_exam(exam_id: UUID, body: ExamDetailsIn, actor: Me):
        return ExamOut.of(module.exams.update_draft(actor, exam_id, body.to_domain()))

    @router.put("/exams/{exam_id}/items", response_model=ExamOut)
    def assign_items(exam_id: UUID, body: PaperIn, actor: Me):
        requests = [SlotRequest(i.question_id, i.max_marks, i.version_id) for i in body.items]
        return ExamOut.of(module.exams.assign(actor, exam_id, requests))

    @router.post("/exams/{exam_id}/publish", response_model=ExamOut)
    def publish_exam(exam_id: UUID, actor: Me):
        return ExamOut.of(module.exams.publish(actor, exam_id))

    @router.post("/exams/{exam_id}/preview", response_model=SandboxOut)
    def preview_exam(exam_id: UUID, actor: Me):
        """SR03 sandbox: a candidate-shaped paper. Nothing is written."""
        return SandboxOut.of(module.sandbox.open(actor, exam_id))

    # -- roster (FR06) ----------------------------------------------------------
    @router.get("/exams/{exam_id}/enrollments", response_model=RosterOut)
    def get_roster(exam_id: UUID, actor: Me):
        return RosterOut.of(module.roster.roster(actor, exam_id))

    @router.post("/exams/{exam_id}/enrollments", response_model=RosterOut)
    def enroll(exam_id: UUID, body: EnrollIn, actor: Me):
        return RosterOut.of(module.roster.enroll(actor, exam_id, body.candidate_emails))

    @router.patch("/exams/{exam_id}/enrollments/{candidate_id}", response_model=RosterOut)
    def set_enrollment(exam_id: UUID, candidate_id: UUID, body: EnrollmentPatch, actor: Me):
        return RosterOut.of(module.roster.set_active(actor, exam_id, candidate_id, body.active))

    @router.post("/exams/{exam_id}/enrollments/import", response_model=ImportReportOut)
    async def import_roster(exam_id: UUID, request: Request, actor: Me, dry_run: bool = False):
        return await run_import(module.roster_import, actor, request, dry_run, exam_id=exam_id)

    # -- question bank (FR04) ---------------------------------------------------
    @router.get("/questions", response_model=list[QuestionOut])
    def search_questions(actor: Me, q: Annotated[str, Query(max_length=200)] = "",
                         topic: Annotated[str, Query(max_length=200)] = "",
                         difficulty: Difficulty | None = None, kind: QuestionKind | None = None):
        found = module.bank.search(actor, BankQuery(q, topic, difficulty, kind))
        return [QuestionOut.of(question) for question in found]

    @router.post("/questions", response_model=QuestionOut, status_code=201)
    def create_question(body: QuestionIn, actor: Me):
        return QuestionOut.of(module.bank.create(actor, _content(body)))

    @router.get("/questions/{question_id}", response_model=QuestionDetailOut)
    def get_question(question_id: UUID, actor: Me):
        return QuestionDetailOut.of(*module.bank.get(actor, question_id))

    @router.post("/questions/{question_id}/versions", response_model=RevisionOut)
    def revise_question(question_id: UUID, body: QuestionIn, actor: Me, response: Response):
        question, _, created = module.bank.revise(actor, question_id, _content(body))
        response.status_code = 201 if created else 200
        return RevisionOut(question=QuestionOut.of(question), created=created)

    @router.post("/questions/import", response_model=ImportReportOut)
    async def import_questions(request: Request, actor: Me, dry_run: bool = False):
        return await run_import(module.question_import, actor, request, dry_run)

    # -- candidate accounts (SR04, via the foundation identity service) ---------
    @router.post("/admin/accounts/import", response_model=ImportReportOut)
    async def import_candidates(request: Request, actor: Me, dry_run: bool = False):
        return await run_import(module.candidate_import, actor, request, dry_run)

    return router
