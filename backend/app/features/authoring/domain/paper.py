"""The frozen paper that authoring hands to delivery, and its candidate-safe view.

``FrozenPaper`` is server-side only: it carries keys and rubrics for the
results-owned grading policy. ``candidate_items`` is the only projection that
may cross into a candidate response (FR05, NFR01).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from .exam import Exam
from .question import QuestionVersion
from .values import MarkingRule, QuestionKind


@dataclass(frozen=True)
class CandidateOption:
    id: int
    label: str


@dataclass(frozen=True)
class CandidateItem:
    """What a candidate may see for one slot. No key, rule or rubric."""

    slot: int
    kind: QuestionKind
    prompt: str
    max_marks: Decimal
    options: tuple[CandidateOption, ...]


@dataclass(frozen=True)
class FrozenItem:
    slot: int
    max_marks: Decimal
    version: QuestionVersion

    @property
    def marking_rule(self) -> MarkingRule:
        return self.version.content.marking_rule

    @property
    def correct_option_ids(self) -> tuple[int, ...]:
        return self.version.content.correct_ids

    def for_candidate(self) -> CandidateItem:
        content = self.version.content
        return CandidateItem(self.slot, content.kind, content.prompt, self.max_marks,
                             tuple(CandidateOption(o.id, o.label) for o in content.options))


@dataclass(frozen=True)
class FrozenPaper:
    """Immutable snapshot of a paper. Delivery builds attempts from it."""

    exam_id: UUID
    title: str
    instructions: str
    opens_at: datetime
    closes_at: datetime
    duration_seconds: int
    total_marks: Decimal
    shuffle_questions: bool
    shuffle_choices: bool
    published_at: datetime | None
    items: tuple[FrozenItem, ...]

    @classmethod
    def of(cls, exam: Exam, versions: dict[UUID, QuestionVersion]) -> "FrozenPaper":
        d = exam.details
        return cls(
            exam.id, d.title, d.instructions, d.schedule.opens_at, d.schedule.closes_at,
            d.schedule.duration_seconds, d.total_marks, d.shuffle_questions, d.shuffle_choices,
            exam.published_at,
            tuple(FrozenItem(i.slot, i.max_marks, versions[i.version_id]) for i in exam.items),
        )

    def candidate_items(self) -> tuple[CandidateItem, ...]:
        return tuple(item.for_candidate() for item in self.items)
