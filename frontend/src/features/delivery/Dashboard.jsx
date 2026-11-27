import React, { useEffect, useState } from "react";
import { PageHead } from "../../design/Folio.jsx";
import Engraving from "./Engraving.jsx";
import { request } from "./api.js";

const groups = ["available", "upcoming", "completed"];
const format = (value, options) => new Date(value).toLocaleString(undefined, options);
const day = { month: "short", day: "numeric" };
const time = { hour: "numeric", minute: "2-digit" };
const navigateTo = (path) => window.location.assign(path);

function windowLabel(exam) {
  const sameDay = new Date(exam.opens_at).toDateString() === new Date(exam.closes_at).toDateString();
  return format(exam.opens_at, time) + " – " + format(exam.closes_at, sameDay ? time : { ...day, ...time });
}

const dateKey = (value) => {
  const d = new Date(value);
  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, "0"),
    String(d.getDate()).padStart(2, "0"),
  ].join("-");
};

function OpeningCalendar({ exams, selected, select }) {
  const counts = new Map();
  for (const exam of exams) {
    const key = dateKey(exam.opens_at);
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  const months = [...new Set([...counts.keys()].map((k) => k.slice(0, 7)))].sort();
  const today = dateKey(new Date());
  const [chosen, setChosen] = useState(null);
  const month = months.includes(chosen)
    ? chosen
    : months.find((m) => m >= today.slice(0, 7)) || months.at(-1);
  const monthIndex = months.indexOf(month);
  const [year, number] = month.split("-").map(Number);
  const first = new Date(year, number - 1, 1);
  const days = new Date(year, number, 0).getDate();
  const offset = (first.getDay() + 6) % 7;
  return (
    <aside className="dv-calendar-index" aria-label="Filter exams by opening date">
      <div className="dv-calendar-top">
        <span>Opening dates</span>
        <h2>{format(first, { month: "long", year: "numeric" })}</h2>
      </div>
      <div className="dv-month-grid">
        {["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"].map((d) => (
          <span className="dv-weekday" key={d}>
            {d}
          </span>
        ))}
        {Array.from({ length: offset }, (_, n) => (
          <span key={"pad" + n} aria-hidden="true" />
        ))}
        {Array.from({ length: days }, (_, n) => {
          const key = month + "-" + String(n + 1).padStart(2, "0"),
            count = counts.get(key);
          return count ? (
            <button
              key={key}
              aria-pressed={key === selected}
              aria-current={key === today ? "date" : undefined}
              aria-label={
                format(new Date(year, number - 1, n + 1), { dateStyle: "long" }) +
                ", " +
                count +
                (count === 1 ? " exam" : " exams")
              }
              onClick={() => select(selected === key ? null : key)}
            >
              {n + 1}
            </button>
          ) : (
            <span key={key}>{n + 1}</span>
          );
        })}
      </div>
      <div className="dv-calendar-actions">
        <button className="quiet" onClick={() => select(null)} disabled={!selected}>
          All dates
        </button>
        {months.length > 1 && (
          <div className="row">
            <button
              className="secondary"
              aria-label="Previous exam month"
              disabled={!monthIndex}
              onClick={() => setChosen(months[monthIndex - 1])}
            >
              Previous
            </button>
            <button
              className="secondary"
              aria-label="Next exam month"
              disabled={monthIndex === months.length - 1}
              onClick={() => setChosen(months[monthIndex + 1])}
            >
              Next
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}

function ExamEntry({ exam, entering, onEnter, featured }) {
  return (
    <article className={"dv-entry" + (featured ? " dv-ticket" : "")}>
      <time
        className="dv-calendar"
        dateTime={exam.opens_at}
        aria-label={format(exam.opens_at, { dateStyle: "long" })}
      >
        {featured && <Engraving />}
        <span>{format(exam.opens_at, { month: featured ? "long" : "short" })}</span>
        <b>{format(exam.opens_at, { day: "2-digit" })}</b>
        <small>{format(exam.opens_at, { weekday: featured ? "long" : "short" })}</small>
      </time>
      <div className="dv-entry-copy">
        <h3>{exam.title}</h3>
        <div className="dv-entry-meta">
          <span>{windowLabel(exam)}</span>
          {exam.duration_seconds > 0 && <span>{Math.ceil(exam.duration_seconds / 60)} min allowance</span>}
          {exam.status === "available" && exam.deadline_at && (
            <span>Attempt due {format(exam.deadline_at, time)}</span>
          )}
        </div>
        {exam.instructions && <p>{exam.instructions}</p>}
      </div>
      <div className="dv-entry-action">
        {exam.status === "available" && (
          <button className="primary" disabled={Boolean(entering)} onClick={() => onEnter(exam)}>
            {entering === exam.id ? "Opening…" : exam.attempt_id ? "Resume attempt" : "Start exam"}
          </button>
        )}
        {exam.status === "completed" &&
          (exam.attempt_id ? (
            <a className="secondary" href={"/attempts/" + exam.attempt_id}>
              View receipt
            </a>
          ) : (
            <span>Entry closed</span>
          ))}
        {exam.status === "upcoming" && <span>Opens {format(exam.opens_at, time)}</span>}
      </div>
    </article>
  );
}

export function CandidateExams({ navigate = navigateTo }) {
  const [exams, setExams] = useState(null);
  const [error, setError] = useState("");
  const [entering, setEntering] = useState(null);
  const [selectedDate, selectDate] = useState(null);
  const [version, retry] = useState(0);
  useEffect(() => {
    let active = true,
      reading = false,
      timer;
    async function refresh() {
      if (!active || reading) return;
      reading = true;
      try {
        const list = await request("/me/exams");
        if (active) {
          setExams(list);
          setError("");
        }
      } catch (cause) {
        if (active) {
          if ([401, 403, 404].includes(cause.status)) setExams(null);
          setError("Could not refresh your exam register.");
        }
      } finally {
        reading = false;
        if (active) {
          clearTimeout(timer);
          timer = setTimeout(refresh, 30000);
        }
      }
    }
    refresh();
    window.addEventListener("focus", refresh);
    window.addEventListener("online", refresh);
    return () => {
      active = false;
      clearTimeout(timer);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("online", refresh);
    };
  }, [version]);
  async function enter(exam) {
    setEntering(exam.id);
    try {
      const attempt = await request("/exams/" + exam.id + "/attempts", "POST");
      navigate("/attempts/" + attempt.attempt_id);
    } catch {
      setError("Could not enter this exam. Refresh the register to check availability.");
    } finally {
      setEntering(null);
    }
  }
  const listed = (exams ?? []).filter(e => !selectedDate || dateKey(e.opens_at) === selectedDate);
  const featured = listed.find(e => e.status === "available") ?? listed.find(e => e.status === "upcoming");
  return (
    <main className="shell dv dv-register">
      <PageHead
        crumb="Candidate workspace"
        title="My exams"
        details={
          exams && (
            <>
              {exams.length} assigned {exams.length === 1 ? "examination" : "examinations"}
            </>
          )
        }
        aside={
          <span className="dv-zone">
            Schedule time zone <b>{Intl.DateTimeFormat().resolvedOptions().timeZone}</b>
          </span>
        }
      />
      {error && (
        <div className="dv-notice" role="alert">
          {error}{" "}
          <button className="quiet" onClick={() => retry((v) => v + 1)}>
            Refresh
          </button>
        </div>
      )}
      {!exams && !error && (
        <p className="dv-notice" role="status">
          Loading assignments…
        </p>
      )}
      {exams?.length === 0 && (
        <section className="dv-empty">
          <h2>No assigned exams</h2>
          <p>Your schedule will appear here when you are enrolled.</p>
        </section>
      )}
      {Boolean(exams?.length) && (
        <div className="dv-register-grid">
          <div>
            {selectedDate && (
              <p className="dv-filter" role="status">
                Opening {format(selectedDate + "T12:00:00", { dateStyle: "long" })}{" "}
                <button className="quiet" onClick={() => selectDate(null)}>
                  Show all exams
                </button>
              </p>
            )}
            {groups.map((group) => {
              const entries = listed.filter(e => e.status === group);
              return (
                entries?.length > 0 && (
                  <section className={"dv-group dv-group-" + group} key={group}>
                    <div className="dv-group-head">
                      <h2>
                        {group === "available"
                          ? "Available now"
                          : group === "upcoming"
                            ? "Upcoming"
                            : "Completed"}
                      </h2>
                      <span>{String(entries.length).padStart(2, "0")}</span>
                    </div>
                    {entries.map((exam) => (
                      <ExamEntry key={exam.id} exam={exam} entering={entering} onEnter={enter} featured={exam === featured} />
                    ))}
                  </section>
                )
              );
            })}
          </div>
          <OpeningCalendar exams={exams} selected={selectedDate} select={selectDate} />
        </div>
      )}
    </main>
  );
}
