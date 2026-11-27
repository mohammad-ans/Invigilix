"""SQLAlchemy Core descriptions of the contract tables authoring reads and writes.

They mirror contracts/exam_schema.sql exactly; the foundation's Alembic
migration remains the source of DDL. ``create_all`` is used only by tests.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Integer,
    MetaData, Numeric, SmallInteger, Table, Text, TypeDecorator, UniqueConstraint, Uuid,
)


class UtcDateTime(TypeDecorator):
    """TIMESTAMPTZ that always returns aware UTC datetimes, on every dialect."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not stored.")
        value = value.astimezone(timezone.utc)
        return value if dialect.name == "postgresql" else value.replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else \
            value.astimezone(timezone.utc)


metadata = MetaData()
Marks = Numeric(8, 2, asdecimal=True)

account = Table(
    "account", metadata,
    Column("id", Uuid, primary_key=True),
    Column("email", Text, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("font_percent", SmallInteger, nullable=False, default=100),
    Column("workspace_layout", Text, nullable=False, default="standard"),
)

account_role = Table(
    "account_role", metadata,
    Column("account_id", Uuid, ForeignKey("account.id"), primary_key=True),
    Column("role_name", Text, primary_key=True),
)

question = Table(
    "question", metadata,
    Column("id", Uuid, primary_key=True),
    Column("owner_id", Uuid, ForeignKey("account.id"), nullable=False),
)

question_version = Table(
    "question_version", metadata,
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
    "question_option", metadata,
    Column("version_id", Uuid, ForeignKey("question_version.id"), primary_key=True),
    Column("option_no", SmallInteger, primary_key=True),
    Column("label", Text, nullable=False),
    Column("is_correct", Boolean, nullable=False),
)

exam = Table(
    "exam", metadata,
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
    "exam_item", metadata,
    Column("exam_id", Uuid, ForeignKey("exam.id"), primary_key=True),
    Column("slot", SmallInteger, primary_key=True),
    Column("version_id", Uuid, ForeignKey("question_version.id"), nullable=False),
    Column("max_marks", Marks, nullable=False),
    UniqueConstraint("exam_id", "version_id"),
    UniqueConstraint("exam_id", "slot", "version_id"),
    CheckConstraint("max_marks > 0"),
)

enrollment = Table(
    "enrollment", metadata,
    Column("exam_id", Uuid, ForeignKey("exam.id"), primary_key=True),
    Column("candidate_id", Uuid, ForeignKey("account.id"), primary_key=True),
    Column("enrolled_by", Uuid, ForeignKey("account.id"), nullable=False),
    Column("active", Boolean, nullable=False, default=True),
)

# Referenced only so tests can assert the sandbox never creates attempts.
attempt = Table(
    "attempt", metadata,
    Column("id", Uuid, primary_key=True),
    Column("exam_id", Uuid, nullable=False),
    Column("candidate_id", Uuid, nullable=False),
    Column("started_at", UtcDateTime, nullable=False),
    Column("deadline_at", UtcDateTime, nullable=False),
    Column("finalized_at", UtcDateTime),
    Column("close_reason", Text),
    ForeignKeyConstraint(["exam_id", "candidate_id"],
                         ["enrollment.exam_id", "enrollment.candidate_id"]),
)
