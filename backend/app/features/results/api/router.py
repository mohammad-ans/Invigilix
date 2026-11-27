"""FastAPI router for results, live monitoring, grading, PDF reports, and verification.

The platform mounts the router returned by :func:`build_router` and supplies
``current_actor``, which enforces authenticated sessions (401) and CSRF checks.
Annotations stay evaluated (no ``from __future__ import annotations``) so
FastAPI resolves the closure-local ``Me`` dependency alias accurately.
"""
from typing import Annotated, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.concurrency import run_in_threadpool

from ..ports import Actor
from ..services import ResultsModule
from .errors import ResultsRoute
from .schemas import (
    AnnouncementIn,
    AnnouncementOut,
    CandidateResultOut,
    ExamResultsOut,
    GradeIn,
    GradeUpdateOut,
    MarkingQueueOut,
    MonitorOut,
    VerifyReportIn,
    VerifyReportOut,
)


def _pdf_response(filename: str, pdf_bytes: bytes) -> Response:
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


def build_router(
    module: ResultsModule,
    current_actor: Callable[..., Actor],
) -> APIRouter:
    router = APIRouter(route_class=ResultsRoute, tags=["results"])
    Me = Annotated[Actor, Depends(current_actor)]

    # -- Monitoring & announcements (FR10, AT06) ------------------------------
    @router.get("/exams/{exam_id}/monitor", response_model=MonitorOut)
    def get_exam_monitor(exam_id: UUID, actor: Me):
        return MonitorOut.of(module.monitor.get_monitor(actor, exam_id))

    @router.get("/exams/{exam_id}/announcements", response_model=list[AnnouncementOut])
    def list_exam_announcements(exam_id: UUID, actor: Me):
        return [
            AnnouncementOut.of(a)
            for a in module.monitor.list_announcements(actor, exam_id)
        ]

    @router.post(
        "/exams/{exam_id}/announcements",
        response_model=AnnouncementOut,
        status_code=201,
    )
    def post_exam_announcement(exam_id: UUID, body: AnnouncementIn, actor: Me):
        return AnnouncementOut.of(
            module.monitor.post_announcement(actor, exam_id, body.message)
        )

    # -- Manual grading (FR11, AT07) ------------------------------------------
    @router.get("/exams/{exam_id}/marking", response_model=MarkingQueueOut)
    def get_exam_marking_queue(exam_id: UUID, actor: Me):
        return MarkingQueueOut.of(module.grading.get_marking_queue(actor, exam_id))

    @router.put("/attempts/{attempt_id}/items/{slot}/grade", response_model=GradeUpdateOut)
    def grade_attempt_item(attempt_id: UUID, slot: int, body: GradeIn, actor: Me):
        return GradeUpdateOut.of(
            module.grading.grade_written_item(actor, attempt_id, slot, body.awarded_marks)
        )

    # -- Results, analytics & release (FR12, SR05, AT07, AT08) ----------------
    @router.get("/exams/{exam_id}/results", response_model=ExamResultsOut)
    def get_exam_results(exam_id: UUID, actor: Me):
        return ExamResultsOut.of(module.results.get_exam_results(actor, exam_id))

    @router.post("/exams/{exam_id}/results/publish", response_model=ExamResultsOut)
    async def publish_exam_results(exam_id: UUID, actor: Me):
        view = await run_in_threadpool(module.results.publish_results, actor, exam_id)
        return ExamResultsOut.of(view)

    # -- PDF exports & candidate results (FR12, SR02, SR06, AT09) -------------
    @router.get("/exams/{exam_id}/report")
    async def download_class_report(exam_id: UUID, actor: Me):
        dl = await run_in_threadpool(module.reports.download_class_report, actor, exam_id)
        return _pdf_response(dl.filename, dl.pdf_bytes)

    @router.get("/me/attempts/{attempt_id}/result", response_model=CandidateResultOut)
    def get_my_attempt_result(attempt_id: UUID, actor: Me):
        return CandidateResultOut.of(module.results.get_candidate_result(actor, attempt_id))

    @router.get("/me/attempts/{attempt_id}/report")
    def download_my_attempt_report(attempt_id: UUID, actor: Me):
        dl = module.reports.download_candidate_report(actor, attempt_id)
        return _pdf_response(dl.filename, dl.pdf_bytes)

    # -- Public verification (SR06, AT09) -------------------------------------
    @router.post("/reports/verify", response_model=VerifyReportOut)
    def verify_report(body: VerifyReportIn):
        return VerifyReportOut(
            valid=module.reports.verify_report(body.verification_code, body.sha256_hex)
        )

    return router
