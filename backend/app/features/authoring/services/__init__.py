"""Application services and the module facade the platform composes."""
from __future__ import annotations

from ..domain import EntryPolicy, PublicationPolicy
from .bank import QuestionBankService
from .base import IdFactory, UnitOfWorkFactory
from .exams import ExamService, SlotRequest
from .imports import CandidateImport, CsvImport, ImportReport, QuestionImport, RosterImport
from .roster import RosterService
from .sandbox import SandboxService


class AuthoringModule:
    """Composition root for the feature. The platform builds one per process with
    its unit-of-work factory; the router and delivery's start use case consume it."""

    def __init__(self, unit_of_work: UnitOfWorkFactory, ids: IdFactory | None = None) -> None:
        self.exams = ExamService(unit_of_work, ids, PublicationPolicy())
        self.bank = QuestionBankService(unit_of_work, ids)
        self.roster = RosterService(unit_of_work, ids, EntryPolicy())
        self.sandbox = SandboxService(unit_of_work, ids)
        self.question_import = QuestionImport(unit_of_work, ids)
        self.roster_import = RosterImport(unit_of_work, ids)
        self.candidate_import = CandidateImport(unit_of_work, ids)


__all__ = [
    "AuthoringModule", "CandidateImport", "CsvImport", "ExamService", "ImportReport",
    "QuestionBankService", "QuestionImport", "RosterImport", "RosterService", "SandboxService",
    "SlotRequest",
]
