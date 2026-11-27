import React from "react";
import { paperProfile, percent, timetable, windowPlan } from "../domain/insights.js";
import { centsToMarks } from "../domain/rules.js";
import { formatDuration, formatWindow, KIND, STATE } from "../domain/format.js";

const time = iso => new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

/**
 * The exam window drawn as a ruler. The solid stretch is when a candidate can
 * still start and receive the full duration; the hatched stretch is when a
 * start is cut short at closing. The caption says the same in words.
 */
export function WindowTimeline({ opens, closes, duration }) {
  const plan = windowPlan(opens, closes, duration);
  if (!plan.valid) return null;
  const full = plan.fullShare * 100;
  return <figure className="au-window" aria-label="Exam window plan">
    <div className="au-window__ends"><span>Opens <b>{time(opens)}</b></span><span>Closes <b>{time(closes)}</b></span></div>
    <div className="au-window__bar" aria-hidden="true">
      {full > 0 && <span className="au-window__full" style={{ width: `${full}%` }} />}
      <span className="au-window__short" style={{ width: `${100 - full}%` }} />
      {full > 0 && full < 100 && <span className="au-window__mark" style={{ left: `${full}%` }}><em>{time(plan.lastFullStart)}</em></span>}
    </div>
    <figcaption className="au-window__caption">
      {plan.durationExceedsWindow
        ? <><b aria-hidden="true">!</b> The {formatDuration(plan.durationMinutes)} duration is longer than the {formatDuration(plan.windowMinutes)} window, so every attempt ends at closing.</>
        : plan.fullMinutes === 0
          ? <><b aria-hidden="true">◷</b> Only candidates who start at {time(opens)} get the full {formatDuration(plan.durationMinutes)}. Any later start ends at {time(closes)}.</>
          : <><b aria-hidden="true">✓</b> Starts until {time(plan.lastFullStart)} get the full {formatDuration(plan.durationMinutes)}. Later starts end at {time(closes)}.</>}
    </figcaption>
  </figure>;
}

function Distribution({ title, groups, label }) {
  const present = groups.filter(g => g.cents > 0);
  return <div className="au-dist">
    <div className="au-dist__head"><span className="mini">{title}</span></div>
    <div className="au-dist__bar" aria-hidden="true">
      {present.map(g => <span key={g.key} className={`au-dist__seg au-dist__seg--${g.key}`} style={{ width: percent(g.share) }} />)}
    </div>
    <ul className="au-dist__legend">{groups.map(g => <li key={g.key} className={g.cents ? "" : "none"}>
      <i className={`au-dist__swatch au-dist__seg--${g.key}`} aria-hidden="true" />
      <span>{label(g.key)}</span><span className="au-mono">{centsToMarks(g.cents)} · {percent(g.share)}</span>
    </li>)}</ul>
  </div>;
}

/** Where the paper's marks sit: difficulty, type, topic and marking workload. */
export function PaperProfile({ slots }) {
  if (!slots.length) return <p className="au-sub">Add questions to see how the marks are spread.</p>;
  const p = paperProfile(slots);
  if (!p.total) return <p className="au-sub">Enter slot marks to see how they are spread.</p>;
  return <div className="au-profile">
    <p className="au-profile__workload">
      <strong className="au-mono">{centsToMarks(p.automatic)}</strong> marks score automatically at finalization;{" "}
      <strong className="au-mono">{centsToMarks(p.manual)}</strong> wait for an examiner.
    </p>
    <Distribution title="Difficulty, by marks" groups={p.difficulty} label={k => k[0].toUpperCase() + k.slice(1)} />
    <Distribution title="Question type, by marks" groups={p.kind} label={k => KIND[k]?.label ?? k} />
    <div className="au-dist">
      <div className="au-dist__head"><span className="mini">Topics, by marks</span></div>
      <ul className="au-topics">{p.topics.map(t => <li key={t.key}>
        <span className="au-topics__name">{t.key}</span>
        <span className="au-topics__track" aria-hidden="true"><span style={{ width: percent(t.share) }} /></span>
        <span className="au-mono">{percent(t.share)}</span>
      </li>)}</ul>
    </div>
  </div>;
}

/**
 * Exam timetable: a fortnight of ruled day columns, weekends shaded, a red
 * "now" line, and each exam window drawn as a bar in its state's style.
 * Every bar is also a link with its title and window in text.
 */
export function ExamTimetable({ exams, onOpen, now = new Date(), days = 14 }) {
  const t = timetable(exams, now, days);
  return <section className="au-timetable" aria-labelledby="timetable-title">
    <div className="split"><h2 id="timetable-title" className="au-subhead">Exam timetable · next {days} days</h2>
      {t.hidden > 0 && <span className="au-sub">{t.hidden} outside this fortnight</span>}</div>
    <div className="au-timetable__grid">
      <div className="au-timetable__days" aria-hidden="true">
        {t.columns.map((c, i) => <span key={i} className={`${c.weekend ? "we" : ""}${c.today ? " today" : ""}`}>
          <b>{c.date.toLocaleDateString(undefined, { weekday: "narrow" })}</b>{c.date.getDate()}</span>)}
      </div>
      <div className="au-timetable__rows">
        <div className="au-timetable__ruling" aria-hidden="true">{t.columns.map((c, i) => <i key={i} className={c.weekend ? "we" : ""} />)}</div>
        <span className="au-timetable__now" style={{ left: `${t.nowLeft}%` }} aria-hidden="true"><em>now</em></span>
        {t.rows.length === 0 && <p className="au-sub au-timetable__none">No exam windows in the next {days} days.</p>}
        <ul>{t.rows.map(r => <li key={r.exam.id}>
          <a href="#" className={`au-timetable__bar au-timetable__bar--${r.exam.state}`} style={{ marginLeft: `${r.left}%`, width: `max(${r.width}%, 8px)` }}
            onClick={e => { e.preventDefault(); onOpen(r.exam); }}>
            <span className="sr-only">{r.exam.title}, {STATE[r.exam.state]?.label}, {formatWindow(r.exam.opens_at, r.exam.closes_at)}</span>
          </a>
          <span className="au-timetable__label" style={{ marginLeft: `min(${r.left}%, calc(100% - 180px))` }} aria-hidden="true">
            <b>{r.exam.title}</b> {formatWindow(r.exam.opens_at, r.exam.closes_at)}</span>
        </li>)}</ul>
      </div>
    </div>
  </section>;
}
