"""Results, monitoring, grading, analytics, and PDF verification feature."""
from .adapters import (
    InMemoryResultsStore,
    ReportLabPdfRenderer,
    SqlResultsUnitOfWork,
    metadata,
    sql_uow_factory,
)
from .api import build_router
from .domain import (
    compute_attempt_total,
    score_finalized_item,
    score_objective,
)
from .ports import ADMIN, Actor, CANDIDATE, EXAMINER, PdfRenderer, ResultsUnitOfWork
from .services import ResultsModule

__all__ = [
    "ADMIN",
    "Actor",
    "CANDIDATE",
    "EXAMINER",
    "InMemoryResultsStore",
    "PdfRenderer",
    "ReportLabPdfRenderer",
    "ResultsModule",
    "ResultsUnitOfWork",
    "SqlResultsUnitOfWork",
    "build_router",
    "compute_attempt_total",
    "metadata",
    "score_finalized_item",
    "score_objective",
    "sql_uow_factory",
]
