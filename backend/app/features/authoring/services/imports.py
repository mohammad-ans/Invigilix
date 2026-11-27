"""Bulk CSV import (SR04): validate every row first, then commit atomically.

Each importer is a :class:`CsvImport` subclass that only knows how to plan one
row. The base class owns parsing, header checks, duplicate detection, row-located
issues and the single transaction, so invalid files leave zero changes and a
repeated file creates no duplicates.
"""
from __future__ import annotations

import csv
import io
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Hashable
from uuid import UUID

from ..domain import (
    AnswerOption, Difficulty, Exam, Issue, MarkingRule, Question, QuestionContent, QuestionKind,
    ValidationFailed,
)
from ..ports import ADMIN, EXAMINER, Actor, UnitOfWork
from .base import AuthoringService
from .roster import RosterService, candidate_issue

MAX_ROWS = 5000
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class CsvRow:
    number: int  # 1-based line in the file; the header is row 1
    values: dict[str, str]

    def get(self, name: str) -> str:
        return (self.values.get(name) or "").strip()


@dataclass(frozen=True)
class CsvTable:
    rows: tuple[CsvRow, ...]

    @classmethod
    def parse(cls, data: bytes, required: tuple[str, ...], optional: tuple[str, ...]) -> "CsvTable":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValidationFailed([Issue("not_utf8", f"The file is not UTF-8 (byte {error.start}).",
                                          field="file")], code="import_invalid") from error
        reader = csv.DictReader(io.StringIO(text, newline=""), restkey="__extra__")
        header = [h.strip() for h in (reader.fieldnames or [])]
        reader.fieldnames = header
        issues = [Issue("missing_column", f"Add the “{name}” column.", field=name, row=1)
                  for name in required if name not in header]
        issues += [Issue("unknown_column", f"Remove or rename the “{name}” column.", field=name,
                         row=1)
                   for name in header if name not in required + optional]
        if len(set(header)) != len(header):
            issues.append(Issue("duplicate_column", "Each column may appear once.", field="header",
                                row=1))
        if issues:
            raise ValidationFailed(issues, "The header row does not match the template.",
                                   code="import_invalid")
        rows = []
        try:
            for values in reader:
                if any((v or "").strip() for k, v in values.items() if k != "__extra__"):
                    rows.append(CsvRow(reader.line_num, values))
                if len(rows) > MAX_ROWS:
                    raise ValidationFailed([Issue("too_many_rows",
                                                  f"Split files above {MAX_ROWS} rows.",
                                                  field="file")], code="import_invalid")
        except csv.Error as error:
            raise ValidationFailed([Issue("malformed_csv", str(error), field="file",
                                          row=reader.line_num)], code="import_invalid") from error
        if not rows:
            raise ValidationFailed([Issue("empty_file", "The file has no data rows.", field="file")],
                                   code="import_invalid")
        return cls(tuple(rows))


@dataclass
class RowPlan:
    """What committing one row will do. ``apply`` runs only if every row is valid."""

    key: Hashable
    action: str  # created | updated | unchanged
    apply: Callable[[UnitOfWork], Any] = lambda uow: None


@dataclass
class ImportReport:
    rows: int
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    committed: bool = False
    issues: list[Issue] = field(default_factory=list)
    credentials: list[tuple[str, str]] = field(default_factory=list)


class CsvImport(AuthoringService, ABC):
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    key_field: str = ""

    def run(self, actor: Actor, data: bytes, *, commit: bool, **scope: Any) -> ImportReport:
        self.authorize(actor)
        table = CsvTable.parse(data, self.required, self.optional)
        with self._uow() as uow:
            context = self.open_scope(uow, actor, **scope)
            plans, issues, seen = [], [], {}
            for row in table.rows:
                if row.values.get("__extra__"):
                    issues.append(Issue("extra_values", "This row has more values than the "
                                        "header. Quote values that contain commas.",
                                        field="row", row=row.number))
                    continue
                try:
                    plan = self.plan(uow, actor, context, row)
                except ValidationFailed as error:
                    issues.extend(i.located(row=row.number) for i in error.issues)
                    continue
                if plan.key in seen:
                    issues.append(Issue("duplicate_row", f"Repeats row {seen[plan.key]}.",
                                        field=self.key_field, row=row.number))
                    continue
                seen[plan.key] = row.number
                plans.append(plan)
            report = ImportReport(len(table.rows), issues=issues)
            for plan in plans:
                setattr(report, plan.action, getattr(report, plan.action) + 1)
            if issues:
                if commit:
                    raise ValidationFailed(issues, "No rows were imported. Fix the listed rows "
                                           "and import the file again.", code="import_invalid")
                return report
            if commit:
                for plan in plans:
                    self.collect(report, plan.apply(uow))
                uow.commit()
                report.committed = True
            return report

    @abstractmethod
    def authorize(self, actor: Actor) -> None: ...

    def open_scope(self, uow: UnitOfWork, actor: Actor, **scope: Any) -> Any:
        return None

    @abstractmethod
    def plan(self, uow: UnitOfWork, actor: Actor, context: Any, row: CsvRow) -> RowPlan: ...

    def collect(self, report: ImportReport, outcome: Any) -> None:
        """Hook for importers that return data from ``apply`` (e.g. credentials)."""


# --------------------------------------------------------------------------- questions
def _json_list(row: CsvRow, name: str) -> list:
    raw = row.get(name) or "[]"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise ValidationFailed([Issue("invalid_json", "Use a JSON array, e.g. [1, 2].",
                                      field=name)])
    if not isinstance(value, list):
        raise ValidationFailed([Issue("invalid_json", "Use a JSON array.", field=name)])
    return value


def _enum(row: CsvRow, name: str, enum: type) -> Any:
    try:
        return enum(row.get(name).lower())
    except ValueError:
        allowed = ", ".join(e.value for e in enum)
        raise ValidationFailed([Issue("invalid_choice", f"Use one of: {allowed}.", field=name)])


def question_content_from_row(row: CsvRow) -> QuestionContent:
    issues: list[Issue] = []
    parsed: dict[str, Any] = {}
    for name, enum in (("difficulty", Difficulty), ("kind", QuestionKind),
                       ("marking_rule", MarkingRule)):
        try:
            parsed[name] = _enum(row, name, enum)
        except ValidationFailed as error:
            issues.extend(error.issues)
    options: list[AnswerOption] = []
    try:
        raw_options, keys = _json_list(row, "options"), _json_list(row, "correct_option_ids")
        if not all(isinstance(k, int) and not isinstance(k, bool) for k in keys):
            issues.append(Issue("invalid_key", "Keys must be integer option IDs.",
                                field="correct_option_ids"))
        for entry in raw_options:
            if not (isinstance(entry, dict) and isinstance(entry.get("id"), int)
                    and not isinstance(entry.get("id"), bool) and isinstance(entry.get("label"), str)):
                issues.append(Issue("invalid_option", 'Each option is {"id": 1, "label": "…"}.',
                                    field="options"))
                break
            options.append(AnswerOption(entry["id"], entry["label"], entry["id"] in keys))
        unknown = sorted(set(k for k in keys if isinstance(k, int)) - {o.id for o in options})
        if unknown and not issues:
            issues.append(Issue("unknown_key", f"Keys {unknown} match no option ID.",
                                field="correct_option_ids"))
    except ValidationFailed as error:
        issues.extend(error.issues)
    if issues:
        raise ValidationFailed(issues)
    content = QuestionContent(row.get("topic"), parsed["difficulty"], parsed["kind"],
                              row.get("prompt"), parsed["marking_rule"], tuple(options),
                              row.get("rubric") or None)
    return content.validated()


class QuestionImport(CsvImport):
    """Examiner bank import. A known ID with new content appends a version."""

    required = ("question_id", "topic", "difficulty", "kind", "prompt", "marking_rule",
                "options", "correct_option_ids")
    optional = ("rubric",)
    key_field = "question_id"

    def authorize(self, actor: Actor) -> None:
        self._require(actor, EXAMINER)

    def plan(self, uow, actor, context, row):
        try:
            question_id = UUID(row.get("question_id"))
        except ValueError:
            raise ValidationFailed([Issue("invalid_uuid", "Use a UUID question ID.",
                                          field="question_id")])
        content = question_content_from_row(row)
        existing = uow.questions.get(question_id, lock=True)
        if existing is None:
            return RowPlan(question_id, "created", lambda u: u.questions.add(
                Question.create(question_id, actor.id, self._ids(), content)))
        if not existing.owned_by(actor.id):
            raise ValidationFailed([Issue("id_in_use", "This question ID is already in use.",
                                          field="question_id")])
        if existing.latest.content == content:
            return RowPlan(question_id, "unchanged")

        def revise(u: UnitOfWork) -> None:
            version, _ = existing.revise(self._ids(), content)
            u.questions.append_version(existing, version)
        return RowPlan(question_id, "updated", revise)


# --------------------------------------------------------------------------- roster
class RosterImport(CsvImport):
    """Examiner roster import for one owned exam."""

    required = ("candidate_email",)
    key_field = "candidate_email"

    def authorize(self, actor: Actor) -> None:
        self._require(actor, EXAMINER)

    def open_scope(self, uow, actor, *, exam_id: UUID) -> Exam:
        exam = self._owned_exam(uow, actor, exam_id, lock=True)
        RosterService.ensure_roster_open(exam, uow)
        return exam

    def plan(self, uow, actor, exam: Exam, row):
        account, issue = candidate_issue(uow, row.get("candidate_email"), "candidate_email")
        if issue:
            raise ValidationFailed([issue])
        current = uow.enrollments.get(exam.id, account.id)
        action = ("created" if current is None else "unchanged" if current.active else "updated")
        return RowPlan(account.id, action,
                       lambda u: RosterService.admit(u, exam, account.id, actor.id))


# --------------------------------------------------------------------------- candidates
class CandidateImport(CsvImport):
    """Administrator account import through the foundation identity service.
    Initial credentials are returned once, in the committing response only."""

    required = ("email", "display_name")
    key_field = "email"

    def authorize(self, actor: Actor) -> None:
        self._require(actor, ADMIN)

    def plan(self, uow, actor, context, row):
        email, name = row.get("email"), row.get("display_name")
        issues = []
        if not EMAIL.match(email):
            issues.append(Issue("invalid_email", "Enter a valid email address.", field="email"))
        if not name:
            issues.append(Issue("required", "Enter a display name.", field="display_name"))
        if issues:
            raise ValidationFailed(issues)
        key = email.casefold()
        existing = uow.accounts.by_email(email)
        if existing is not None:
            if not existing.is_candidate:
                raise ValidationFailed([Issue("email_in_use", "This email belongs to a "
                                              "non-candidate account.", field="email")])
            return RowPlan(key, "unchanged")
        return RowPlan(key, "created", lambda u: u.accounts.provision_candidate(email, name))

    def collect(self, report, outcome):
        if outcome is not None:
            report.credentials.append((outcome.account.email, outcome.initial_password))
