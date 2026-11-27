"""Enrollment and eligibility use cases (FR06)."""
from __future__ import annotations

from uuid import UUID

from ..domain import (
    Conflict, EntryDecision, EntryPolicy, Enrollment, Exam, ExamState, Issue, NotFound,
    ValidationFailed,
)
from ..ports import CANDIDATE, EXAMINER, Actor, UnitOfWork
from .base import AuthoringService, IdFactory, UnitOfWorkFactory
from .views import CandidateExamEntry, RosterEntry, RosterView


def candidate_issue(uow: UnitOfWork, email: str, field: str) -> tuple[object, Issue | None]:
    """Resolve an email to an enrollable candidate or explain why it is not one."""
    account = uow.accounts.by_email(email) if email.strip() else None
    if not email.strip():
        return None, Issue("required", "Enter the candidate's email.", field=field)
    if account is None:
        return None, Issue("unknown_candidate", "No account uses this email.", field=field)
    if not account.is_candidate:
        return None, Issue("not_candidate", "This account does not hold the candidate role.",
                           field=field)
    if not account.enabled:
        return None, Issue("account_disabled", "This account is disabled.", field=field)
    return account, None


class RosterService(AuthoringService):
    def __init__(self, unit_of_work: UnitOfWorkFactory, ids: IdFactory | None = None,
                 policy: EntryPolicy | None = None) -> None:
        super().__init__(unit_of_work, ids)
        self._policy = policy or EntryPolicy()

    # -- examiner --------------------------------------------------------------
    def roster(self, actor: Actor, exam_id: UUID) -> RosterView:
        self._require(actor, EXAMINER)
        with self._uow() as uow:
            return self._view(uow, self._owned_exam(uow, actor, exam_id))

    def enroll(self, actor: Actor, exam_id: UUID, emails: list[str]) -> RosterView:
        """Enroll each email, reactivating withdrawn entries. All or nothing."""
        self._require(actor, EXAMINER)
        with self._uow() as uow:
            exam = self._owned_exam(uow, actor, exam_id, lock=True)
            self.ensure_roster_open(exam, uow)
            issues, accounts = [], []
            for index, email in enumerate(emails, start=1):
                account, issue = candidate_issue(uow, email, "candidate_email")
                if issue:
                    issues.append(issue.located(row=index))
                elif account not in accounts:
                    accounts.append(account)
            if issues or not accounts:
                raise ValidationFailed(issues or [Issue("required", "Enter at least one email.",
                                                        field="candidate_email")])
            for account in accounts:
                self.admit(uow, exam, account.id, actor.id)
            view = self._view(uow, exam)
            uow.commit()
            return view

    def set_active(self, actor: Actor, exam_id: UUID, candidate_id: UUID,
                   active: bool) -> RosterView:
        """Withdraw or restore an enrollment. History is deactivated, never deleted."""
        self._require(actor, EXAMINER)
        with self._uow() as uow:
            exam = self._owned_exam(uow, actor, exam_id, lock=True)
            self.ensure_roster_open(exam, uow)
            enrollment = uow.enrollments.get(exam.id, candidate_id)
            if enrollment is None:
                raise NotFound("Enrollment")
            enrollment.active = active
            uow.enrollments.save(enrollment)
            view = self._view(uow, exam)
            uow.commit()
            return view

    # -- candidate and delivery boundary ---------------------------------------
    def assigned_exams(self, actor: Actor) -> list[CandidateExamEntry]:
        """Published exams the candidate may see, with their access status."""
        self._require(actor, CANDIDATE)
        with self._uow() as uow:
            now = uow.now()
            account = uow.accounts.by_ids([actor.id]).get(actor.id)
            enrollments = {e.exam_id: e for e in uow.enrollments.for_candidate(actor.id)}
            entries = []
            for exam in uow.exams.get_many(enrollments):
                decision = self._policy.decide(exam, account, enrollments[exam.id], now)
                if decision.visible_to_candidate:
                    entries.append(CandidateExamEntry(exam, decision))
            return sorted(entries, key=lambda e: e.exam.details.schedule.opens_at)

    def entry_decision(self, actor: Actor, exam_id: UUID) -> EntryDecision:
        """Delivery calls this inside start. Inaccessible exams are 404, never described."""
        with self._uow() as uow:
            exam = uow.exams.get(exam_id)
            account = uow.accounts.by_ids([actor.id]).get(actor.id)
            enrollment = uow.enrollments.get(exam_id, actor.id) if exam else None
            if exam is None:
                raise NotFound("Exam")
            decision = self._policy.decide(exam, account, enrollment, uow.now())
            if not decision.visible_to_candidate:
                raise NotFound("Exam")
            return decision

    # -- shared helpers (also used by the roster CSV import) --------------------
    @staticmethod
    def ensure_roster_open(exam: Exam, uow: UnitOfWork) -> None:
        if exam.state_at(uow.now()) is ExamState.COMPLETED:
            raise Conflict("exam_closed", "The exam has closed. Its roster is now a record.")

    @staticmethod
    def admit(uow: UnitOfWork, exam: Exam, candidate_id: UUID, by: UUID) -> str:
        existing = uow.enrollments.get(exam.id, candidate_id)
        if existing is None:
            uow.enrollments.add(Enrollment(exam.id, candidate_id, by))
            return "created"
        if not existing.active:
            existing.active = True
            uow.enrollments.save(existing)
            return "updated"
        return "unchanged"

    def _view(self, uow: UnitOfWork, exam: Exam) -> RosterView:
        now = uow.now()
        enrollments = uow.enrollments.for_exam(exam.id)
        accounts = uow.accounts.by_ids(e.candidate_id for e in enrollments)
        entries = [RosterEntry(accounts[e.candidate_id], e,
                               self._policy.decide(exam, accounts[e.candidate_id], e, now))
                   for e in enrollments if e.candidate_id in accounts]
        entries.sort(key=lambda r: (not r.enrollment.active, r.account.display_name.casefold()))
        return RosterView(exam, exam.state_at(now), tuple(entries), now)
