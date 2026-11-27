"""Adapters for results: SQLAlchemy Core, in-memory store, and ReportLab PDF renderer."""
from .memory import InMemoryResultsStore, InMemoryResultsUnitOfWork
from .pdf import ReportLabPdfRenderer
from .sql import SqlResultsUnitOfWork, sql_uow_factory
from .sql_tables import metadata

__all__ = [
    "InMemoryResultsStore",
    "InMemoryResultsUnitOfWork",
    "ReportLabPdfRenderer",
    "SqlResultsUnitOfWork",
    "metadata",
    "sql_uow_factory",
]
