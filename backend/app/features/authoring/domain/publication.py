"""Publication policy: the checklist a draft must pass before it is frozen (FR05)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping
from uuid import UUID

from .errors import Issue
from .exam import Exam
from .question import QuestionVersion


@dataclass(frozen=True)
class AssignedVersion:
    """A pinned version together with the owner of its bank question."""

    version: QuestionVersion
    owner_id: UUID


@dataclass(frozen=True)
class Check:
    """One named rule with its outcome, shown to the examiner as a checklist row."""

    name: str
    label: str
    issues: tuple[Issue, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class PublicationReport:
    checks: tuple[Check, ...]

    @property
    def ready(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def issues(self) -> tuple[Issue, ...]:
        return tuple(i for c in self.checks for i in c.issues)


class PublicationPolicy:
    """Evaluates a draft against every publication rule without mutating it."""

    def review(self, exam: Exam, bank: Mapping[UUID, AssignedVersion],
               now: datetime) -> PublicationReport:
        return PublicationReport((
            self._particulars(exam),
            self._window(exam, now),
            self._nonempty(exam),
            self._ownership(exam, bank),
            self._distinct(exam),
            self._keys(exam, bank),
            self._total(exam),
        ))

    @staticmethod
    def _particulars(exam: Exam) -> Check:
        issues = list(exam.details.schedule.issues())
        if not exam.details.title.strip():
            issues.append(Issue("required", "Enter a title.", field="title"))
        return Check("particulars", "Title, window and duration are valid", tuple(issues))

    @staticmethod
    def _window(exam: Exam, now: datetime) -> Check:
        issues = ()
        if exam.details.schedule.closes_at <= now:
            issues = (Issue("window_passed", "The closing time has already passed.",
                            field="closes_at"),)
        return Check("window", "The exam has not closed yet", issues)

    @staticmethod
    def _nonempty(exam: Exam) -> Check:
        issues = () if exam.items else (
            Issue("empty_paper", "Add at least one question to the paper.", field="items"),)
        return Check("nonempty", "The paper has at least one question", issues)

    @staticmethod
    def _ownership(exam: Exam, bank: Mapping[UUID, AssignedVersion]) -> Check:
        issues = []
        for item in exam.items:
            entry = bank.get(item.version_id)
            if entry is None or entry.owner_id != exam.owner_id:
                issues.append(Issue("question_unavailable",
                                    "This question is not in your bank.",
                                    field="question_id", item=item.slot))
        return Check("ownership", "Every question comes from your bank", tuple(issues))

    @staticmethod
    def _distinct(exam: Exam) -> Check:
        issues, seen = [], set()
        for item in exam.items:
            if item.question_id in seen:
                issues.append(Issue("duplicate_question", "A bank question may appear only once.",
                                    field="question_id", item=item.slot))
            seen.add(item.question_id)
        return Check("distinct", "Each bank question appears once", tuple(issues))

    @staticmethod
    def _keys(exam: Exam, bank: Mapping[UUID, AssignedVersion]) -> Check:
        issues = []
        for item in exam.items:
            entry = bank.get(item.version_id)
            if entry is not None:
                issues.extend(i.located(item=item.slot) for i in entry.version.content.issues())
        return Check("keys", "Options and answer keys are valid", tuple(issues))

    @staticmethod
    def _total(exam: Exam) -> Check:
        issues = []
        for item in exam.items:
            if item.max_marks <= 0:
                issues.append(Issue("non_positive_marks", "Marks must be greater than zero.",
                                    field="max_marks", item=item.slot))
        allocated, declared = exam.allocated_marks, exam.details.total_marks
        if exam.items and allocated != declared:
            issues.append(Issue("total_mismatch",
                                f"Item marks add up to {allocated} but the declared total is "
                                f"{declared}.", field="total_marks"))
        return Check("total", "Item marks add up to the declared total", tuple(issues))
