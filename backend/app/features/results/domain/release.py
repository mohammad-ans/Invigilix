"""Release gating, exam status derivation, and verification code helpers (FR12, SR06)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Iterable, Mapping
from uuid import UUID

from .errors import Conflict, Issue
from .values import AttemptItemRecord, AttemptRecord, ExamRecord, ExamStatus


def derive_exam_status(exam: ExamRecord, now: datetime) -> ExamStatus:
    """Derive exam lifecycle status from publication fields and authoritative DB time."""
    if exam.published_at is None:
        return "draft"
    if exam.results_published_at is not None:
        return "results_released"
    if now < exam.opens_at:
        return "scheduled"
    if now < exam.closes_at:
        return "ongoing"
    return "closed"


def release_blockers(
    exam: ExamRecord,
    attempts: Iterable[AttemptRecord],
    items_by_attempt: dict[UUID, list[AttemptItemRecord]],
    now: datetime,
    labels: Mapping[UUID, str] | None = None,
) -> list[Issue]:
    """Return every unmet condition preventing result release for ``exam``.

    ``labels`` maps attempt IDs to the candidate's display name so the examiner
    reads "Sana Ali · slot 3" instead of an opaque attempt UUID.
    """
    issues: list[Issue] = []
    name = lambda attempt_id: (labels or {}).get(attempt_id) or f"Attempt {attempt_id}"
    if exam.published_at is None:
        issues.append(Issue("exam_not_published", "Exam has not been published yet."))
        return issues

    if exam.results_published_at is not None:
        issues.append(
            Issue(
                "results_already_released",
                "Results have already been released for this exam.",
                field="results_published_at",
            )
        )
        return issues

    if now < exam.closes_at:
        issues.append(
            Issue(
                "exam_not_closed",
                "Results cannot be released until the scheduled exam close time has passed.",
                field="closes_at",
            )
        )

    attempt_list = list(attempts)
    unfinalized = [a for a in attempt_list if a.finalized_at is None]
    if unfinalized:
        issues.append(
            Issue(
                "attempts_not_finalized",
                f"{len(unfinalized)} real attempt(s) must be finalized before releasing results.",
            )
        )

    for a in attempt_list:
        if a.finalized_at is None:
            continue
        items = items_by_attempt.get(a.id, ())
        if not items:
            issues.append(
                Issue(
                    "grading_incomplete",
                    f"{name(a.id)} has no assigned items to grade.",
                )
            )
            continue
        for it in items:
            if it.awarded_marks is None:
                issues.append(
                    Issue(
                        "grading_incomplete",
                        f"{name(a.id)} · slot {it.slot} still awaits a manual grade.",
                        field="awarded_marks",
                        item=it.slot,
                    )
                )

    return issues


def require_release_ready(
    exam: ExamRecord,
    attempts: Iterable[AttemptRecord],
    items_by_attempt: dict[UUID, list[AttemptItemRecord]],
    now: datetime,
    labels: Mapping[UUID, str] | None = None,
) -> None:
    """Raise Conflict if any FR12 release gate fails."""
    issues = release_blockers(exam, attempts, items_by_attempt, now, labels)
    if issues:
        primary = issues[0]
        raise Conflict(primary.code, primary.message, issues)


def generate_verification_code() -> str:
    """Generate a URL-safe verification code with 192 bits (>= 128 bits) of CSPRNG entropy."""
    return secrets.token_urlsafe(24)


def compute_sha256_hex(data: bytes) -> str:
    """Return the lowercase 64-char SHA-256 hex digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def constant_time_digest_match(expected_hex: str, provided_hex: str) -> bool:
    """Verify two SHA-256 hex digests without leaking timing differences."""
    return hmac.compare_digest(expected_hex.lower(), provided_hex.strip().lower())
