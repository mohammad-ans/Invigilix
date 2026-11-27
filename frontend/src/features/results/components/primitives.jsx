import React from "react";
import { PageHead, SaveStatus } from "../../../design/Folio.jsx";
import { ATTEMPT_STATUS_META, EXAM_STATUS_LABEL } from "../domain/rules.js";
import { paths } from "../paths.js";

export { PageHead, SaveStatus };

export function StatusPill({ tone = "muted", glyph, label }) {
  return (
    <span className={`badge res-badge-${tone}`}>
      {glyph ? <span aria-hidden="true">{glyph} </span> : null}
      {label}
    </span>
  );
}

export function AttemptStatusBadge({ status }) {
  const meta = ATTEMPT_STATUS_META[status] ?? { label: status, tone: "muted", glyph: "•" };
  return <StatusPill tone={meta.tone} glyph={meta.glyph} label={meta.label} />;
}

export function ExamStatusPill({ status }) {
  const tone =
    status === "ongoing" || status === "results_released"
      ? "sage"
      : status === "closed"
        ? "amber"
        : "muted";
  return <StatusPill tone={tone} label={EXAM_STATUS_LABEL[status] ?? status} />;
}

export function Banner({ tone = "sage", title, children, role = "status" }) {
  return (
    <div className={`res-banner res-banner--${tone}`} role={role}>
      {title ? <h3 className="res-banner-title">{title}</h3> : null}
      <div className="res-banner-body">{children}</div>
    </div>
  );
}

export function EmptyPanel({ title, detail }) {
  return (
    <div className="event" role="status">
      <strong>{title}</strong>
      {detail ? <p className="res-muted">{detail}</p> : null}
    </div>
  );
}

export function ExaminerTabs({ examId, active, navigate }) {
  const tabs = [
    { id: "monitor", label: "Monitor", to: paths.monitor(examId) },
    { id: "marking", label: "Marking", to: paths.marking(examId) },
    { id: "results", label: "Results & analytics", to: paths.results(examId) },
  ];
  return (
    <nav className="res-tabs" aria-label="Examiner exam tools">
      {tabs.map(t => (
        <a
          key={t.id}
          href={"#" + t.to}
          className="res-tab"
          aria-current={active === t.id ? "page" : undefined}
          onClick={e => {
            if (!navigate) return;
            e.preventDefault();
            navigate(t.to);
          }}
        >
          {t.label}
        </a>
      ))}
    </nav>
  );
}

export function triggerPdfDownload({ blob, filename }) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || "report.pdf";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
