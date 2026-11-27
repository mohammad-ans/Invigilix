"""Request and response bodies. Marks travel as fixed-point strings ("10.00").

Examiner responses carry keys and rubrics because the examiner owns them. The
only candidate-facing shape here, :class:`SandboxItemOut`, mirrors the attempt
item in contracts/attempt-api.md and has no key, rule or rubric field.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from ..domain import (
    AnswerOption, Check, Difficulty, ExamDetails, ExamState, Issue, MarkingRule, Question,
    QuestionContent, QuestionKind, QuestionVersion,
)
from ..services import ImportReport
from ..services.views import (
    ExamOverview, ExamSummary, QuestionUsage, RosterView, SandboxPaper, SlotView,
)

Text = Annotated[str, StringConstraints(max_length=20_000)]
Line = Annotated[str, StringConstraints(max_length=300)]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ----------------------------------------------------------------------------- requests
class ExamDetailsIn(In):
    title: Line
    instructions: Text = ""
    opens_at: AwareDatetime
    closes_at: AwareDatetime
    duration_minutes: int = Field(ge=-10**6, le=10**6)
    total_marks: Decimal
    shuffle_questions: bool = False
    shuffle_choices: bool = False

    def to_domain(self) -> ExamDetails:
        return ExamDetails.build(**self.model_dump())


class SlotIn(In):
    question_id: UUID
    max_marks: Decimal
    version_id: UUID | None = None


class PaperIn(In):
    items: list[SlotIn] = Field(max_length=200)


class OptionIn(In):
    id: int
    label: Line


class QuestionIn(In):
    topic: Line
    difficulty: Difficulty
    kind: QuestionKind
    prompt: Text
    marking_rule: MarkingRule
    options: list[OptionIn] = Field(default_factory=list, max_length=26)
    correct_option_ids: list[int] = Field(default_factory=list, max_length=26)
    rubric: Text | None = None

    def to_domain(self) -> QuestionContent:
        keys = set(self.correct_option_ids)
        return QuestionContent(self.topic, self.difficulty, self.kind, self.prompt,
                               self.marking_rule,
                               tuple(AnswerOption(o.id, o.label, o.id in keys)
                                     for o in self.options), self.rubric)

    def unknown_keys(self) -> list[int]:
        return sorted(set(self.correct_option_ids) - {o.id for o in self.options})


class EnrollIn(In):
    candidate_emails: list[Line] = Field(min_length=1, max_length=500)


class EnrollmentPatch(In):
    active: bool


# ----------------------------------------------------------------------------- responses
class IssueOut(BaseModel):
    code: str
    message: str
    field: str | None = None
    item: int | None = None
    row: int | None = None

    @classmethod
    def of(cls, issue: Issue) -> "IssueOut":
        return cls(**issue.__dict__)


class CheckOut(BaseModel):
    name: str
    label: str
    passed: bool
    issues: list[IssueOut]

    @classmethod
    def of(cls, check: Check) -> "CheckOut":
        return cls(name=check.name, label=check.label, passed=check.passed,
                   issues=[IssueOut.of(i) for i in check.issues])


class PublicationOut(BaseModel):
    ready: bool
    checks: list[CheckOut]


class OptionOut(BaseModel):
    id: int
    label: str
    correct: bool


class VersionOut(BaseModel):
    id: UUID
    number: int
    topic: str
    difficulty: Difficulty
    kind: QuestionKind
    prompt: str
    marking_rule: MarkingRule
    options: list[OptionOut]
    correct_option_ids: list[int]
    rubric: str | None

    @classmethod
    def of(cls, version: QuestionVersion) -> "VersionOut":
        c = version.content
        return cls(id=version.id, number=version.number, topic=c.topic, difficulty=c.difficulty,
                   kind=c.kind, prompt=c.prompt, marking_rule=c.marking_rule,
                   options=[OptionOut(id=o.id, label=o.label, correct=o.correct)
                            for o in c.options],
                   correct_option_ids=list(c.correct_ids), rubric=c.rubric)


class QuestionOut(BaseModel):
    id: UUID
    version_count: int
    latest: VersionOut

    @classmethod
    def of(cls, question: Question) -> "QuestionOut":
        return cls(id=question.id, version_count=len(question.versions),
                   latest=VersionOut.of(question.latest))


class UsageOut(BaseModel):
    exam_id: UUID
    exam_title: str
    slot: int
    version_number: int
    frozen: bool

    @classmethod
    def of(cls, usage: QuestionUsage) -> "UsageOut":
        return cls(**usage.__dict__)


class QuestionDetailOut(BaseModel):
    id: UUID
    versions: list[VersionOut]
    usage: list[UsageOut]

    @classmethod
    def of(cls, question: Question, usage: list[QuestionUsage]) -> "QuestionDetailOut":
        return cls(id=question.id, versions=[VersionOut.of(v) for v in reversed(question.versions)],
                   usage=[UsageOut.of(u) for u in usage])


class RevisionOut(BaseModel):
    question: QuestionOut
    created: bool


class SlotOut(BaseModel):
    slot: int
    max_marks: Decimal
    question_id: UUID
    version: VersionOut
    latest_version_number: int
    outdated: bool

    @classmethod
    def of(cls, view: SlotView) -> "SlotOut":
        return cls(slot=view.item.slot, max_marks=view.item.max_marks,
                   question_id=view.item.question_id, version=VersionOut.of(view.version),
                   latest_version_number=view.latest_number, outdated=view.outdated)


class ExamFields(BaseModel):
    id: UUID
    title: str
    instructions: str
    opens_at: datetime
    closes_at: datetime
    duration_minutes: int
    total_marks: Decimal
    allocated_marks: Decimal
    shuffle_questions: bool
    shuffle_choices: bool
    state: ExamState
    published_at: datetime | None

    @staticmethod
    def fields(exam, state: ExamState) -> dict:
        d = exam.details
        return dict(id=exam.id, title=d.title, instructions=d.instructions,
                    opens_at=d.schedule.opens_at, closes_at=d.schedule.closes_at,
                    duration_minutes=d.schedule.duration_seconds // 60, total_marks=d.total_marks,
                    allocated_marks=exam.allocated_marks, shuffle_questions=d.shuffle_questions,
                    shuffle_choices=d.shuffle_choices, state=state,
                    published_at=exam.published_at)


class ExamSummaryOut(ExamFields):
    item_count: int
    enrolled: int

    @classmethod
    def of(cls, summary: ExamSummary) -> "ExamSummaryOut":
        return cls(**cls.fields(summary.exam, summary.state), item_count=len(summary.exam.items),
                   enrolled=summary.enrolled)


class ExamOut(ExamFields):
    server_time: datetime
    items: list[SlotOut]
    publication: PublicationOut

    @classmethod
    def of(cls, view: ExamOverview) -> "ExamOut":
        return cls(**cls.fields(view.exam, view.state), server_time=view.server_time,
                   items=[SlotOut.of(s) for s in view.slots],
                   publication=PublicationOut(ready=view.report.ready,
                                              checks=[CheckOut.of(c) for c in view.report.checks]))


class RosterEntryOut(BaseModel):
    candidate_id: UUID
    email: str
    display_name: str
    active: bool
    access: str
    can_start: bool


class RosterOut(BaseModel):
    exam_id: UUID
    state: ExamState
    server_time: datetime
    entries: list[RosterEntryOut]

    @classmethod
    def of(cls, view: RosterView) -> "RosterOut":
        return cls(exam_id=view.exam.id, state=view.state, server_time=view.server_time,
                   entries=[RosterEntryOut(candidate_id=e.account.id, email=e.account.email,
                                           display_name=e.account.display_name,
                                           active=e.enrollment.active, access=e.decision.access,
                                           can_start=e.decision.can_start)
                            for e in view.entries])


class CredentialOut(BaseModel):
    email: str
    initial_password: str


class ImportReportOut(BaseModel):
    rows: int
    created: int
    updated: int
    unchanged: int
    committed: bool
    issues: list[IssueOut]
    credentials: list[CredentialOut] = Field(default_factory=list)

    @classmethod
    def of(cls, report: ImportReport) -> "ImportReportOut":
        return cls(rows=report.rows, created=report.created, updated=report.updated,
                   unchanged=report.unchanged, committed=report.committed,
                   issues=[IssueOut.of(i) for i in report.issues],
                   credentials=[CredentialOut(email=e, initial_password=p)
                                for e, p in report.credentials])


class SandboxOptionOut(BaseModel):
    id: int
    label: str


class SandboxItemOut(BaseModel):
    """Same shape as an attempt item (contracts/attempt-api.md), with empty answers."""

    slot: int
    display_no: int
    kind: QuestionKind
    prompt: str
    max_marks: Decimal
    options: list[SandboxOptionOut]
    selected_option_ids: list[int] = Field(default_factory=list)
    written_answer: str = ""
    flagged: bool = False
    revision: int = 0


class SandboxOut(BaseModel):
    mode: Literal["sandbox"] = "sandbox"
    exam_id: UUID
    title: str
    instructions: str
    total_marks: Decimal
    server_time: datetime
    deadline_at: datetime
    items: list[SandboxItemOut]

    @classmethod
    def of(cls, paper: SandboxPaper) -> "SandboxOut":
        d = paper.exam.details
        return cls(exam_id=paper.exam.id, title=d.title, instructions=d.instructions,
                   total_marks=d.total_marks, server_time=paper.server_time,
                   deadline_at=paper.deadline_at,
                   items=[SandboxItemOut(slot=i.slot, display_no=n, kind=i.kind, prompt=i.prompt,
                                         max_marks=i.max_marks,
                                         options=[SandboxOptionOut(id=o.id, label=o.label)
                                                  for o in i.options])
                          for n, i in enumerate(paper.items, start=1)])
