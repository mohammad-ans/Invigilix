"""PDF export and public cryptographic verification services (SR02, SR06, AT09)."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ..domain import (
    Conflict,
    Issue,
    NotFound,
    ScoreRegister,
    Sha256Digest,
    ValidationFailed,
    VerificationCode,
    compute_class_summary,
    compute_question_analytics,
    constant_time_digest_match,
    derive_exam_status,
)
from ..ports import Actor, CandidateScoreLine, PdfRenderer
from .base import UowFactory, load_owned_exam, require_candidate



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

            candidate_lines = [
                CandidateScoreLine(
                    attempt_id=line.attempt.id,
                    display_name=line.display_name,
                    email=line.email,
                    close_reason=line.attempt.close_reason or "submitted",
                    finalized_at=line.attempt.finalized_at,
                    graded_count=line.graded_count,
                    item_count=line.item_count,
                    total_score=line.total_score,
                )
                for line in ScoreRegister.build(finalized, items_by_attempt, accounts)
            ]
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
        """Verify an issued PDF's code and SHA-256 digest (SR06).

        Both values are read the way a person copies them from paper: the code
        ignores spaces, hyphens, case and look-alikes; the digest ignores
        whitespace. The answer is a validity bit and nothing else.
        """
        issues: list[Issue] = []
        if not str(verification_code or "").strip():
            issues.append(Issue("empty_code", "Verification code is required.", field="verification_code"))
        try:
            digest = Sha256Digest.parse(sha256_hex)
        except ValidationFailed as invalid:
            issues.extend(invalid.issues)
        if issues:
            raise ValidationFailed(issues)
        code = VerificationCode.parse(verification_code)
        if code is None:
            return False
        with self._uow() as uow:
            report = uow.reports.get_by_code(str(code))
            if report is None:
                return False
            return constant_time_digest_match(report.sha256_hex, digest.hex)
