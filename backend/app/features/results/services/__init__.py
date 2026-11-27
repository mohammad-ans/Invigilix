"""Application service facade for the results feature."""
from __future__ import annotations

from ..ports import PdfRenderer
from .base import UowFactory
from .grading import GradeUpdateResult, GradingService, MarkingItemView, MarkingQueueView
from .monitor import (
    AnnouncementView,
    IncidentEventView,
    MonitorCounts,
    MonitorService,
    MonitorSnapshot,
    RosterProgressRow,
)
from .reports import PdfDownload, ReportService
from .results import (
    CandidateAttemptScoreView,
    CandidateResultItemView,
    CandidateResultView,
    CandidateSelectedOptionView,
    ExamResultsView,
    ReleaseBlockerView,
    ResultsService,
)


class ResultsModule:
    """Bundled results services constructed with one UoW factory and PDF renderer."""

    def __init__(self, uow_factory: UowFactory, pdf_renderer: PdfRenderer) -> None:
        self.monitor = MonitorService(uow_factory)
        self.grading = GradingService(uow_factory)
        self.results = ResultsService(uow_factory, pdf_renderer)
        self.reports = ReportService(uow_factory, pdf_renderer)


__all__ = [
    "AnnouncementView",
    "CandidateAttemptScoreView",
    "CandidateResultItemView",
    "CandidateResultView",
    "CandidateSelectedOptionView",
    "ExamResultsView",
    "GradeUpdateResult",
    "GradingService",
    "IncidentEventView",
    "MarkingItemView",
    "MarkingQueueView",
    "MonitorCounts",
    "MonitorService",
    "MonitorSnapshot",
    "PdfDownload",
    "ReleaseBlockerView",
    "ReportService",
    "ResultsModule",
    "ResultsService",
    "RosterProgressRow",
    "UowFactory",
]
