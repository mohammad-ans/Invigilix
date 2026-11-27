"""PDF export and public cryptographic verification services (SR02, SR06, AT09)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from ..domain import (
    Conflict,
    Issue,
    NotFound,
    ValidationFailed,
    compute_attempt_total,
    compute_class_summary,
    compute_question_analytics,
    constant_time_digest_match,
    derive_exam_status,
)
from ..ports import Actor, CandidateScoreLine, PdfRenderer
from .base import UowFactory, load_owned_exam, require_candidate

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PdfDownload:
    filename: str
    pdf_bytes: bytes
    sha256_hex: str | None = None
    verification_code: str | None = None


class ReportService:
    """Downloads issued candidate PDFs, owner class summaries, and verifies hashes."""

    def __init__(self, uow_factory: UowFactory, pdf_renderer: PdfRenderer) -> None:
        self._uow = uow_factory
        self._pdf = pdf_renderer

    def download_candidate_report(self, actor: Actor, attempt_id: UUID) -> PdfDownload:
        require_candidate(actor)
        with self._uow() as uow:
            attempt = uow.attempts.get(attempt_id)
            if attempt is None or attempt.candidate_id != actor.id or attempt.finalized_at is None:
                raise NotFound("Report")

            exam = uow.exams.get(attempt.exam_id)
            if exam is None or exam.results_published_at is None:
                raise NotFound("Report")

            report = uow.reports.get_by_attempt(attempt.id)
            if report is None:
                raise NotFound("Report")

            return PdfDownload(
                filename=f"result-{attempt.id}.pdf",
                pdf_bytes=report.pdf_bytes,
                sha256_hex=report.sha256_hex,
                verification_code=report.verification_code,
            )

    def download_class_report(self, actor: Actor, exam_id: UUID) -> PdfDownload:
        with self._uow() as uow:
            exam = load_owned_exam(uow, actor, exam_id)
            if exam.published_at is None:
                raise Conflict(
                    "exam_not_published",
                    "Publish the exam before generating a class summary report.",
                )

            now = uow.now()
            paper = uow.exams.paper_items(exam.id)
            enrollments = uow.enrollments.for_exam(exam.id)
            attempts = uow.attempts.for_exam(exam.id)
            items_by_attempt = uow.attempts.items_for_exam(exam.id)
            finalized = [a for a in attempts if a.finalized_at is not None]
            accounts = uow.accounts.by_ids(a.candidate_id for a in finalized)

            summary = compute_class_summary(enrollments, attempts, items_by_attempt)
            analytics = compute_question_analytics(paper, finalized, items_by_attempt)

            candidate_lines: list[CandidateScoreLine] = []
            for att in sorted(
                finalized,
                key=lambda a: (
                    accounts.get(a.candidate_id).display_name.lower()
                    if a.candidate_id in accounts
                    else str(a.candidate_id)
                ),
            ):
                items = items_by_attempt.get(att.id, ())
                graded_count = sum(1 for it in items if it.awarded_marks is not None)
                total = compute_attempt_total(it.awarded_marks for it in items)
                acct = accounts.get(att.candidate_id)
                candidate_lines.append(
                    CandidateScoreLine(
                        attempt_id=att.id,
                        display_name=acct.display_name if acct else str(att.candidate_id),
                        email=acct.email if acct else "",
                        close_reason=att.close_reason or "submitted",
                        finalized_at=att.finalized_at,
                        graded_count=graded_count,
                        item_count=len(items),
                        total_score=total,
                    )
                )

            pdf_bytes = self._pdf.render_class_summary(
                exam=exam,
                generated_at=now,
                status=derive_exam_status(exam, now),
                summary=summary,
                candidates=candidate_lines,
                analytics=analytics,
            )
            return PdfDownload(
                filename=f"exam-{exam.id}-summary.pdf",
                pdf_bytes=pdf_bytes,
            )

    def verify_report(self, verification_code: str, sha256_hex: str) -> bool:
        """Verify an issued PDF's verification code and SHA-256 digest (SR06)."""
        issues: list[Issue] = []
        code = verification_code.strip()
        digest = sha256_hex.strip().lower()

        if not code:
            issues.append(
                Issue("empty_code", "Verification code is required.", field="verification_code")
            )
        if not SHA256_RE.fullmatch(digest):
            issues.append(
                Issue(
                    "invalid_digest",
                    "SHA-256 digest must be exactly 64 hexadecimal characters.",
                    field="sha256_hex",
                )
            )
        if issues:
            raise ValidationFailed(issues)

        with self._uow() as uow:
            report = uow.reports.get_by_code(code)
            if report is None:
                return False
            return constant_time_digest_match(report.sha256_hex, digest)
