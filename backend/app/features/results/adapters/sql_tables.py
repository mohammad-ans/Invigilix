"""SQLAlchemy Core table definitions mirroring contracts/exam_schema.sql.

Alembic in the foundation lane owns production DDL; ``metadata.create_all``
is invoked only by isolated feature tests.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    SmallInteger,
    Table,
    Text,
    TypeDecorator,
    UniqueConstraint,
    Uuid,
)


class UtcDateTime(TypeDecorator):
    """TIMESTAMPTZ that consistently yields aware UTC datetimes across backends."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not permitted.")
        utc = value.astimezone(timezone.utc)
        return utc if dialect.name == "postgresql" else utc.replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


metadata = MetaData()
Marks = Numeric(8, 2, asdecimal=True)

account = Table(
    "account",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("email", Text, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("font_percent", SmallInteger, nullable=False, default=100),
    Column("workspace_layout", Text, nullable=False, default="standard"),
)

account_role = Table(
    "account_role",
    metadata,
    Column("account_id", Uuid, ForeignKey("account.id"), primary_key=True),
    Column("role_name", Text, primary_key=True),
)

question = Table(
    "question",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("owner_id", Uuid, ForeignKey("account.id"), nullable=False),
)

question_version = Table(
    "question_version",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("question_id", Uuid, ForeignKey("question.id"), nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("topic", Text, nullable=False),
    Column("difficulty", Text, nullable=False),
    Column("prompt", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("marking_rule", Text, nullable=False),
    Column("rubric", Text),
    UniqueConstraint("question_id", "version_no"),
)

question_option = Table(
    "question_option",
    metadata,
    Column("version_id", Uuid, ForeignKey("question_version.id"), primary_key=True),
    Column("option_no", SmallInteger, primary_key=True),
    Column("label", Text, nullable=False),
    Column("is_correct", Boolean, nullable=False),
)

exam = Table(
    "exam",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("owner_id", Uuid, ForeignKey("account.id"), nullable=False),
    Column("title", Text, nullable=False),
    Column("instructions", Text, nullable=False),
    Column("opens_at", UtcDateTime, nullable=False),
    Column("closes_at", UtcDateTime, nullable=False),
    Column("duration_seconds", Integer, nullable=False),
    Column("total_marks", Marks, nullable=False),
    Column("shuffle_objective", Boolean, nullable=False, default=False),
    Column("shuffle_choices", Boolean, nullable=False, default=False),
    Column("published_at", UtcDateTime),
    Column("results_published_at", UtcDateTime),
    CheckConstraint("closes_at > opens_at"),
    CheckConstraint("duration_seconds > 0"),
    CheckConstraint("total_marks > 0"),
)

exam_item = Table(
    "exam_item",
    metadata,
    Column("exam_id", Uuid, ForeignKey("exam.id"), primary_key=True),
    Column("slot", SmallInteger, primary_key=True),
    Column("version_id", Uuid, ForeignKey("question_version.id"), nullable=False),
    Column("max_marks", Marks, nullable=False),
    UniqueConstraint("exam_id", "version_id"),
    UniqueConstraint("exam_id", "slot", "version_id"),
    CheckConstraint("max_marks > 0"),
)

enrollment = Table(
    "enrollment",
    metadata,
    Column("exam_id", Uuid, ForeignKey("exam.id"), primary_key=True),
    Column("candidate_id", Uuid, ForeignKey("account.id"), primary_key=True),
    Column("enrolled_by", Uuid, ForeignKey("account.id"), nullable=False),
    Column("active", Boolean, nullable=False, default=True),
)

attempt = Table(
    "attempt",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("exam_id", Uuid, nullable=False),
    Column("candidate_id", Uuid, nullable=False),
    Column("started_at", UtcDateTime, nullable=False),
    Column("deadline_at", UtcDateTime, nullable=False),
    Column("finalized_at", UtcDateTime),
    Column("close_reason", Text),
    ForeignKeyConstraint(
        ["exam_id", "candidate_id"],
        ["enrollment.exam_id", "enrollment.candidate_id"],
    ),
    UniqueConstraint("exam_id", "candidate_id"),
    UniqueConstraint("id", "exam_id"),
)

attempt_item = Table(
    "attempt_item",
    metadata,
    Column("attempt_id", Uuid, primary_key=True),
    Column("exam_id", Uuid, nullable=False),
    Column("slot", SmallInteger, primary_key=True),
    Column("version_id", Uuid, nullable=False),
    Column("display_no", SmallInteger, nullable=False),
    Column("written_answer", Text, nullable=False, default=""),
    Column("flagged", Boolean, nullable=False, default=False),
    Column("answer_revision", Integer, nullable=False, default=0),
    Column("saved_at", UtcDateTime),
    Column("awarded_marks", Marks),
    Column("graded_by", Uuid, ForeignKey("account.id")),
    UniqueConstraint("attempt_id", "display_no"),
    UniqueConstraint("attempt_id", "slot", "version_id"),
    ForeignKeyConstraint(["attempt_id", "exam_id"], ["attempt.id", "attempt.exam_id"]),
    ForeignKeyConstraint(
        ["exam_id", "slot", "version_id"],
        ["exam_item.exam_id", "exam_item.slot", "exam_item.version_id"],
    ),
)

attempt_option = Table(
    "attempt_option",
    metadata,
    Column("attempt_id", Uuid, primary_key=True),
    Column("slot", SmallInteger, primary_key=True),
    Column("version_id", Uuid, nullable=False),
    Column("option_no", SmallInteger, primary_key=True),
    Column("display_no", SmallInteger, nullable=False),
    Column("selected", Boolean, nullable=False, default=False),
    UniqueConstraint("attempt_id", "slot", "display_no"),
    ForeignKeyConstraint(
        ["attempt_id", "slot", "version_id"],
        ["attempt_item.attempt_id", "attempt_item.slot", "attempt_item.version_id"],
    ),
    ForeignKeyConstraint(
        ["version_id", "option_no"],
        ["question_option.version_id", "question_option.option_no"],
    ),
)

attempt_event = Table(
    "attempt_event",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("attempt_id", Uuid, ForeignKey("attempt.id"), nullable=False),
    Column("kind", Text, nullable=False),
    Column("recorded_at", UtcDateTime, nullable=False),
    Column("note", Text),
)

announcement = Table(
    "announcement",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("exam_id", Uuid, ForeignKey("exam.id"), nullable=False),
    Column("author_id", Uuid, ForeignKey("account.id"), nullable=False),
    Column("posted_at", UtcDateTime, nullable=False),
    Column("message", Text, nullable=False),
)

result_report = Table(
    "result_report",
    metadata,
    Column("verification_code", Text, primary_key=True),
    Column("attempt_id", Uuid, ForeignKey("attempt.id"), nullable=False, unique=True),
    Column("issued_at", UtcDateTime, nullable=False),
    Column("sha256_hex", Text, nullable=False),
    Column("pdf_bytes", LargeBinary, nullable=False),
)
