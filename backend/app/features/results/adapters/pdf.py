"""ReportLab PDF generator for candidate reports and owner class summaries (SR02, SR06)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import BytesIO
from typing import Sequence

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen.canvas import Canvas

from ..domain import AccountSummary, AttemptRecord, ClassSummary, ExamRecord, QuestionAnalytics
from ..ports import CandidateReportItemLine, CandidateScoreLine, PdfRenderer

PAPER = colors.HexColor("#F6F4EC")
FOREST = colors.HexColor("#183F36")
GRAPHITE = colors.HexColor("#202F2A")
MUTED = colors.HexColor("#53635A")
SAGE = colors.HexColor("#E5EDDF")
RULE = colors.HexColor("#C9CEC0")


def _fmt_dt(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


class _PageLayout:
    """Minimal paginated ReportLab canvas helper styled in Folio's register palette."""

    def __init__(self, title: str, subtitle: str) -> None:
        self.buf = BytesIO()
        self.width, self.height = A4
        self.margin = 44
        self.usable = self.width - 2 * self.margin
        self.canvas = Canvas(self.buf, pagesize=A4, invariant=1)
        self.canvas.setTitle(title)
        self.canvas.setAuthor("Folio Examination Office")
        self.canvas.setSubject(subtitle)
        self.page_no = 1
        self._draw_header(title, subtitle)

    def _draw_header(self, title: str, subtitle: str) -> None:
        c = self.canvas
        c.setFillColor(FOREST)
        c.rect(0, self.height - 54, self.width, 54, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Times-BoldItalic", 18)
        c.drawString(self.margin, self.height - 34, "Folio")
        c.setFont("Helvetica", 9)
        c.drawString(self.margin + 46, self.height - 33, f"Examination office  |  {subtitle}")

        c.setFillColor(GRAPHITE)
        c.setFont("Times-Bold", 18)
        c.drawString(self.margin, self.height - 84, title)
        c.setStrokeColor(GRAPHITE)
        c.setLineWidth(1.5)
        c.line(self.margin, self.height - 94, self.width - self.margin, self.height - 94)
        self.y = self.height - 114
        self._title = title
        self._subtitle = subtitle

    def ensure_space(self, needed: float) -> None:
        if self.y - needed >= 52:
            return
        self._draw_footer()
        self.canvas.showPage()
        self.page_no += 1
        self._draw_header(self._title, self._subtitle)

    def _draw_footer(self) -> None:
        c = self.canvas
        c.setStrokeColor(RULE)
        c.setLineWidth(0.75)
        c.line(self.margin, 38, self.width - self.margin, 38)
        c.setFillColor(MUTED)
        c.setFont("Courier", 8)
        c.drawString(self.margin, 25, "Folio Examination Office  |  Authoritative server record")
        c.drawRightString(self.width - self.margin, 25, f"Page {self.page_no}")

    def section_heading(self, text: str) -> None:
        self.ensure_space(28)
        c = self.canvas
        c.setFillColor(FOREST)
        c.setFont("Times-Bold", 13)
        c.drawString(self.margin, self.y, text)
        self.y -= 6
        c.setStrokeColor(RULE)
        c.setLineWidth(0.75)
        c.line(self.margin, self.y, self.width - self.margin, self.y)
        self.y -= 14

    def key_value_rows(self, pairs: Sequence[tuple[str, str]]) -> None:
        c = self.canvas
        for label, value in pairs:
            wrapped = simpleSplit(value, "Helvetica", 9.5, self.usable - 135) or [""]
            self.ensure_space(len(wrapped) * 13 + 6)
            c.setFillColor(MUTED)
            c.setFont("Courier-Bold", 8.5)
            c.drawString(self.margin, self.y, label.upper())
            c.setFillColor(GRAPHITE)
            c.setFont("Helvetica", 9.5)
            for idx, line in enumerate(wrapped):
                c.drawString(self.margin + 135, self.y - idx * 12, line)
            self.y -= max(14, len(wrapped) * 12 + 4)

    def info_box(self, title: str, body_lines: Sequence[str], *, fill=SAGE) -> None:
        wrapped_all: list[str] = []
        for line in body_lines:
            wrapped_all.extend(simpleSplit(line, "Courier", 8.5, self.usable - 20) or [""])
        box_h = 26 + len(wrapped_all) * 12
        self.ensure_space(box_h + 10)
        c = self.canvas
        c.setFillColor(fill)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.75)
        c.rect(self.margin, self.y - box_h + 12, self.usable, box_h, stroke=1, fill=1)
        c.setFillColor(FOREST)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(self.margin + 10, self.y - 4, title)
        c.setFillColor(GRAPHITE)
        c.setFont("Courier", 8.5)
        cy = self.y - 19
        for line in wrapped_all:
            c.drawString(self.margin + 10, cy, line)
            cy -= 12
        self.y -= box_h + 10

    def wrapped_line(self, text: str, *, font: str = "Helvetica", size: float = 9.5, indent: float = 0) -> None:
        lines = simpleSplit(text, font, size, self.usable - indent) or [""]
        self.ensure_space(len(lines) * (size + 3) + 4)
        c = self.canvas
        c.setFillColor(GRAPHITE)
        c.setFont(font, size)
        for line in lines:
            c.drawString(self.margin + indent, self.y, line)
            self.y -= size + 3
        self.y -= 2

    def finish(self) -> bytes:
        self._draw_footer()
        self.canvas.save()
        return self.buf.getvalue()


class ReportLabPdfRenderer(PdfRenderer):
    """Generates clean, self-contained Folio PDFs via ReportLab."""

    def render_candidate_report(
        self,
        *,
        exam: ExamRecord,
        attempt: AttemptRecord,
        candidate: AccountSummary,
        total_score: Decimal,
        verification_code: str,
        issued_at: datetime,
        items: list[CandidateReportItemLine],
    ) -> bytes:
        doc = _PageLayout(
            title=exam.title,
            subtitle="Official Candidate Result",
        )
        doc.key_value_rows(
            [
                ("Candidate", f"{candidate.display_name} ({candidate.email})"),
                ("Exam ID", str(exam.id)),
                ("Attempt ID", str(attempt.id)),
                ("Finalized", f"{_fmt_dt(attempt.finalized_at)} ({attempt.close_reason})"),
                ("Released", _fmt_dt(issued_at)),
                ("Total Score", f"{total_score:.2f} / {exam.total_marks:.2f}"),
            ]
        )
        doc.info_box(
            f"Final Score: {total_score:.2f} / {exam.total_marks:.2f}",
            [
                f"Verification code: {verification_code}",
                "Verify authenticity at /verify with this code and the SHA-256 digest of this PDF.",
            ],
        )
        doc.section_heading("Itemized Awards (Candidate-Safe Record)")
        for item in items:
            doc.ensure_space(34)
            header = (
                f"Q{item.display_no:02d} (Slot {item.slot}, {item.kind}) — "
                f"Awarded {item.awarded_marks:.2f} / {item.max_marks:.2f}"
            )
            doc.wrapped_line(header, font="Helvetica-Bold", size=9.5)
            doc.wrapped_line(item.prompt, font="Helvetica", size=9.0, indent=12)
        return doc.finish()

    def render_class_summary(
        self,
        *,
        exam: ExamRecord,
        generated_at: datetime,
        status: str,
        summary: ClassSummary,
        candidates: list[CandidateScoreLine],
        analytics: list[QuestionAnalytics],
    ) -> bytes:
        doc = _PageLayout(
            title=f"{exam.title} — Class Summary",
            subtitle="Owner Performance Report",
        )
        doc.key_value_rows(
            [
                ("Exam ID", str(exam.id)),
                ("Lifecycle Status", status),
                ("Generated At", _fmt_dt(generated_at)),
                ("Total Marks", f"{exam.total_marks:.2f}"),
                (
                    "Participation",
                    f"Enrolled: {summary.enrolled_count} | Finalized: {summary.finalized_count} | "
                    f"In Progress: {summary.in_progress_count} | No-Show: {summary.no_show_count}",
                ),
                (
                    "Grading Status",
                    f"Fully Graded: {summary.graded_attempt_count} | Pending: {summary.pending_grading_count}",
                ),
            ]
        )

        if summary.graded_attempt_count > 0:
            stats_line = (
                f"Graded attempts: {summary.graded_attempt_count}   |   "
                f"Mean: {summary.mean_score:.2f} / {exam.total_marks:.2f}   |   "
                f"Median: {summary.median_score:.2f}   |   "
                f"Range: {summary.min_score:.2f} – {summary.max_score:.2f}"
            )
        else:
            stats_line = "No data (0 fully graded finalized attempts)"
        doc.info_box("Class Performance Summary", [stats_line], fill=PAPER)

        doc.section_heading("Candidate Register (Real Finalized Attempts)")
        if not candidates:
            doc.wrapped_line("No data — no finalized real attempts recorded.")
        else:
            for row in candidates:
                score_txt = (
                    f"{row.total_score:.2f} / {exam.total_marks:.2f}"
                    if row.total_score is not None
                    else "Pending grade"
                )
                doc.wrapped_line(
                    f"{row.display_name} <{row.email}> — {score_txt} "
                    f"({row.graded_count}/{row.item_count} graded, {row.close_reason})",
                    font="Helvetica",
                    size=9.0,
                )

        doc.section_heading("Question Analytics")
        if not analytics:
            doc.wrapped_line("No data — no items assigned to this exam.")
        else:
            for q in analytics:
                wrong = (
                    ", ".join(
                        f"{w.label} ({w.count}/{w.exposure_count})"
                        for w in q.common_incorrect_selections
                    )
                    or "None"
                )
                doc.wrapped_line(
                    f"Slot {q.slot:02d} (v{q.version_no}, {q.topic}, {q.kind}, {q.max_marks:.2f} marks) — "
                    f"Exposures: {q.exposure_count} | Skipped: {q.skip_rate_display} | "
                    f"Facility: {q.facility_display} | Common wrong: {wrong}",
                    font="Helvetica",
                    size=8.8,
                )
        return doc.finish()
