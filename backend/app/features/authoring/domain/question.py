"""Question bank aggregate: a question owns an append-only list of versions."""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from .errors import Issue, ValidationFailed
from .values import ALLOWED_RULES, Difficulty, MarkingRule, QuestionKind


@dataclass(frozen=True)
class AnswerOption:
    """One choice in an objective question. ``id`` is stable within its version."""

    id: int
    label: str
    correct: bool = False


@dataclass(frozen=True)
class QuestionContent:
    """Everything a version freezes: prompt, options, private key, rule and rubric."""

    topic: str
    difficulty: Difficulty
    kind: QuestionKind
    prompt: str
    marking_rule: MarkingRule
    options: tuple[AnswerOption, ...] = ()
    rubric: str | None = None

    def normalized(self) -> "QuestionContent":
        rubric = (self.rubric or "").strip() or None
        return QuestionContent(
            topic=self.topic.strip(), difficulty=self.difficulty, kind=self.kind,
            prompt=self.prompt.strip(), marking_rule=self.marking_rule,
            options=tuple(AnswerOption(o.id, o.label.strip(), o.correct) for o in self.options),
            rubric=rubric,
        )

    @property
    def correct_ids(self) -> tuple[int, ...]:
        return tuple(o.id for o in self.options if o.correct)

    def issues(self) -> list[Issue]:
        """Return every rule this content breaks (FR04, FR05)."""
        found: list[Issue] = []
        if not self.topic.strip():
            found.append(Issue("required", "Enter a topic.", field="topic"))
        if not self.prompt.strip():
            found.append(Issue("required", "Enter the question prompt.", field="prompt"))
        if self.marking_rule not in ALLOWED_RULES[self.kind]:
            allowed = ", ".join(sorted(ALLOWED_RULES[self.kind]))
            found.append(Issue("rule_mismatch", f"A {self.kind} question uses {allowed} marking.",
                               field="marking_rule"))
        found.extend(self._option_issues())
        return found

    def _option_issues(self) -> list[Issue]:
        if not self.kind.objective:
            if self.options:
                return [Issue("written_has_options", "Written questions take no options.",
                              field="options")]
            return []
        found: list[Issue] = []
        if len(self.options) < 2:
            found.append(Issue("too_few_options", "Objective questions need at least two options.",
                               field="options"))
        ids = [o.id for o in self.options]
        if any(i <= 0 for i in ids):
            found.append(Issue("invalid_option_id", "Option IDs must be positive integers.",
                               field="options"))
        if len(set(ids)) != len(ids):
            found.append(Issue("duplicate_option_id", "Each option needs a distinct ID.",
                               field="options"))
        if any(not o.label.strip() for o in self.options):
            found.append(Issue("empty_option", "Every option needs a label.", field="options"))
        labels = [o.label.strip().casefold() for o in self.options]
        if len(set(labels)) != len(labels):
            found.append(Issue("duplicate_option_label", "Option labels must differ.",
                               field="options"))
        keys = len(self.correct_ids)
        if self.kind is QuestionKind.SINGLE and keys != 1:
            found.append(Issue("single_key_count",
                               f"Single-answer questions need exactly one key; {keys} marked.",
                               field="correct_option_ids"))
        if self.kind is QuestionKind.MULTIPLE and keys < 1:
            found.append(Issue("multiple_key_count",
                               "Multiple-select questions need at least one key.",
                               field="correct_option_ids"))
        return found

    def validated(self) -> "QuestionContent":
        content = self.normalized()
        issues = content.issues()
        if issues:
            raise ValidationFailed(issues)
        return content


@dataclass(frozen=True)
class QuestionVersion:
    """An immutable revision. Assignments pin a version, never the question."""

    id: UUID
    question_id: UUID
    number: int
    content: QuestionContent


@dataclass
class Question:
    """Aggregate root of the bank. Edits append a version; history never changes."""

    id: UUID
    owner_id: UUID
    versions: list[QuestionVersion] = field(default_factory=list)

    @classmethod
    def create(cls, question_id: UUID, owner_id: UUID, version_id: UUID,
               content: QuestionContent) -> "Question":
        question = cls(question_id, owner_id)
        question.revise(version_id, content)
        return question

    @property
    def latest(self) -> QuestionVersion:
        return self.versions[-1]

    def owned_by(self, account_id: UUID) -> bool:
        return self.owner_id == account_id

    def version(self, version_id: UUID) -> QuestionVersion | None:
        return next((v for v in self.versions if v.id == version_id), None)

    def revise(self, version_id: UUID, content: QuestionContent) -> tuple[QuestionVersion, bool]:
        """Append a version unless ``content`` equals the latest one.

        Returns the effective version and whether it was newly created, so a
        repeated import or a no-op save never produces duplicate history.
        """
        content = content.validated()
        if self.versions and self.latest.content == content:
            return self.latest, False
        version = QuestionVersion(version_id, self.id, len(self.versions) + 1, content)
        self.versions.append(version)
        return version, True
