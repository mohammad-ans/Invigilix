import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { PageHead, SaveStatus } from "../../design/Folio.jsx";
import "../../design/folio.css";
import "./delivery.css";
import { AttemptSession } from "./session.js";
import { visibleItem } from "./queue.js";
import Engraving from "./Engraving.jsx";
export { purgeDeliveryAccount } from "./store.js";

const date = (value) => new Date(value).toLocaleString();
const answered = (item) =>
  item.kind === "written" ? Boolean(item.written_answer.trim()) : item.selected_option_ids.length > 0;
export { CandidateExams } from "./Dashboard.jsx";

function clock(ms) {
  const seconds = Math.max(0, Math.ceil(ms / 1000));
  return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
}

function answerText(item) {
  if (item.kind === "written") return item.written_answer || "Unanswered";
  return (
    item.options
      .filter((o) => item.selected_option_ids.includes(o.id))
      .map((o) => o.label)
      .join(", ") || "Unanswered"
  );
}

function Countdown({ deadline, session, offset, onExpiry }) {
  const read = () => (session.timeLeft ? session.timeLeft() : Date.parse(deadline) - Date.now() - offset);
  const [remaining, setRemaining] = useState(read);
  useEffect(() => {
    const update = () => setRemaining(read());
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [deadline, session, offset]);
  const expired = remaining <= 0;
  useEffect(() => {
    onExpiry(expired);
  }, [expired, onExpiry]);
  const warning = expired
    ? "Time is up"
    : remaining <= 60000
      ? "Final minute"
      : remaining <= 300000
        ? "Five minutes or less"
        : "";
  return (
    <div className={"dv-timer" + (warning ? " dv-timer-urgent" : "")}>
      <span className="clock-label">Time remaining</span>
      <strong role="timer" aria-live="off">
        {clock(remaining)}
      </strong>
      <span className="dv-timer-foot">
        Closes {new Date(deadline).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
      </span>
      <span className="sr-only" role="status">
        {warning}
      </span>
    </div>
  );
}

function Receipt({ state, preview }) {
  const { receipt, outstanding = [] } = state;
  const heading = useRef(null);
  useEffect(() => { heading.current?.focus(); }, []);
  return (
    <main className="shell dv">
      <PageHead
        crumb={preview ? "Examiner preview" : "Candidate workspace"}
        title={receipt.close_reason === "expired" ? "Time expired" : "Attempt submitted"}
        details={state.title}
      />
      <section className="dv-receipt" data-reason={receipt.close_reason} aria-labelledby="receipt-title">
        <header>
          <h2 id="receipt-title" tabIndex={-1} ref={heading}>Final receipt</h2>
          <div className="dv-imprint" aria-hidden="true">
            <Engraving />
            <span>{receipt.close_reason === "expired" ? "Expired" : "Filed"}</span>
          </div>
        </header>
        <dl>
          <dt>Finalized</dt>
          <dd>{date(receipt.finalized_at)}</dd>
          <dt>Recorded as</dt>
          <dd>
            {receipt.close_reason === "expired" ? "Closed at the time limit" : "Submitted by candidate"}
          </dd>
          <dt>Attempt reference</dt>
          <dd className="dv-reference">{receipt.attempt_id}</dd>
        </dl>
        {outstanding.length > 0 && (
          <p className="dv-notice" role="status">
            Unconfirmed local changes on {outstanding.length === 1 ? "question" : "questions"}{" "}
            {outstanding.join(", ")}. The receipt covers answers accepted by the server.
          </p>
        )}
        {!preview && (
          <a className="secondary" href="/me/exams">
            Return to my exams
          </a>
        )}
      </section>
    </main>
  );
}

function ReviewList({ items, record, navigate }) {
  return (
    <ol className="dv-review-list">
      {items.map((q, n) => {
        const sync = record.conflicts[q.slot]
          ? "Conflict"
          : record.pending.some((e) => e.slot === q.slot)
            ? "Awaiting save"
            : "";
        return (
          <li key={q.slot}>
            <button onClick={() => navigate(n)} aria-label={"Edit question " + q.display_no}>
              <span className="dv-index">{String(q.display_no).padStart(2, "0")}</span>
              <span>
                <b>{q.prompt}</b>
                <span className="dv-response">{answerText(q)}</span>
              </span>
              <span className="dv-review-state">
                {[sync, q.flagged ? "Flagged" : ""].filter(Boolean).join(" · ") || "Edit"}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

// Authoring can render this view with an in-memory controller and preview=true.
export function AttemptView({ state, session, preview = false }) {
  // History state is per tab and contains only a position, never answer content.
  const [position, jump] = useState(() => {
    const saved = window.history.state?.deliveryPosition;
    return !preview && saved?.attempt === session.id && Number.isInteger(saved.index) ? saved.index : 0;
  });
  const [review, setReview] = useState(false);
  const [elapsed, setElapsed] = useState(false);
  const [prefBusy, setPrefBusy] = useState(false);
  const reviewHeading = useRef(null),
    prompt = useRef(null);
  const focusQuestion = useRef(false);
  const { record, receipt, error } = state;
  const paper = record?.paper;
  useEffect(() => {
    if (elapsed && !receipt) session.refresh();
  }, [elapsed, session, Boolean(receipt)]);
  useLayoutEffect(() => {
    if (review) reviewHeading.current?.focus();
    else if (focusQuestion.current) prompt.current?.focus();
    focusQuestion.current = false;
  }, [review, position]);
  if (receipt) return <Receipt state={state} preview={preview} />;
  if (!record)
    return (
      <main className="shell dv">
        <PageHead crumb="Candidate workspace" title="Your attempt" />
        <p className="dv-notice" role={error ? "alert" : "status"}>
          {error || "Loading attempt…"}{" "}
          {!state.denied && error && (
            <button className="quiet" onClick={() => session.refresh()}>
              Retry
            </button>
          )}
        </p>
      </main>
    );
  const { pending, conflicts } = record;
  const items = paper.items.map((q) => visibleItem(record, q.slot));
  const index = Math.max(0, Math.min(position, items.length - 1));
  const item = items[index],
    conflict = conflicts[item.slot],
    prefs = paper.preferences;
  const locked = elapsed || state.submitting;
  const count = items.filter(answered).length,
    flagged = items.filter((q) => q.flagged).length;
  const pendingCount = new Set(pending.map((e) => e.slot)).size;
  const type = { single: "Single choice", multiple: "Multiple select", written: "Written response" }[
    item.kind
  ];
  const instruction = {
    single: "Select one answer",
    multiple: "Select all that apply",
    written: "Write your answer",
  }[item.kind];
  const status = preview
    ? "Saved in this preview"
    : state.storageFailed && state.status === "On this device"
      ? "Save failed"
      : state.status;
  function edit(patch) {
    session.edit(item, patch);
  }
  function go(n) {
    if (n === position && !review) prompt.current?.focus();
    else focusQuestion.current = true;
    jump(n);
    setReview(false);
    if (!preview && session.id) {
      window.history.replaceState(
        { ...window.history.state, deliveryPosition: { attempt: session.id, index: n } },
        "",
      );
    }
  }
  async function preference(patch) {
    setPrefBusy(true);
    try {
      await session.preferences({ ...prefs, ...patch });
    } finally {
      setPrefBusy(false);
    }
  }
  return (
    <main
      className={"shell dv " + (prefs.workspace_layout === "focus" ? "focus" : "")}
      style={{ "--reading": prefs.font_percent / 100 + "rem" }}
    >
      <PageHead
        crumb={preview ? "Examiner preview" : "Candidate workspace"}
        title={paper.title}
        details={
          <>
            <span>{items.length} questions</span>
            <i />
            <span>
              {items.reduce((sum, q) => sum + Math.round(Number(q.max_marks) * 100), 0) / 100} total marks
            </span>
          </>
        }
        aside={
          <Countdown
            deadline={paper.deadline_at}
            offset={record.offset}
            session={session}
            onExpiry={setElapsed}
          />
        }
      />
      <a className="dv-jump" href="#delivery-sheet">
        Go to answer sheet
      </a>
      {elapsed && (
        <p className="dv-notice" role="status">
          Time is up. Waiting for the server receipt.
        </p>
      )}
      {state.storageFailed && (
        <p className="dv-notice dv-error" role="alert">
          Local storage unavailable. Unsaved work cannot be recovered after refresh.
        </p>
      )}
      {error && (
        <p className="dv-notice" role="alert">
          {error}{" "}
          <button className="quiet" onClick={() => session.refresh()}>
            Retry
          </button>
        </p>
      )}
      <div className="workgrid">
        <article className="sheet dv-paper" key={review ? "review" : item.slot}>
          {review ? (
            <>
              <div className="dv-sheet-rule">
                <span>Submission review</span>
                <span>{items.length} items</span>
              </div>
              <h2 className="dv-review-title" ref={reviewHeading} tabIndex={-1}>
                Review answers
              </h2>
              <p className="dv-review-count">
                {count} answered · {items.length - count} unanswered · {flagged} flagged
              </p>
              {pendingCount > 0 && (
                <p className="dv-notice" role="status">
                  {pendingCount} {pendingCount === 1 ? "answer has" : "answers have"} changes awaiting server
                  confirmation.
                </p>
              )}
              <ReviewList items={items} record={record} navigate={go} />
              {state.submitBlocked && pendingCount > 0 && (
                <section className="dv-notice" role="alert">
                  <b>Some changes could not be saved.</b>
                  <p>
                    Return to the questions to resolve conflicts, or submit the answers already accepted by
                    the server. Local-only changes will be excluded.
                  </p>
                  <button
                    className="secondary"
                    disabled={locked}
                    onClick={() => session.submit({ acceptedOnly: true })}
                  >
                    Submit saved answers only
                  </button>
                </section>
              )}
              <div className="actions">
                <button className="secondary" onClick={() => go(index)}>
                  Return to question
                </button>
                <button className="primary" disabled={locked} onClick={() => session.submit()}>
                  {state.submitting ? "Submitting…" : "Confirm submission"}
                </button>
              </div>
            </>
          ) : (
            <>
              <header className="dv-paper-head">
                <div className="dv-folio-no">
                  <span>Question</span>
                  <b><span>{String(item.display_no).padStart(2, "0")}</span></b>
                </div>
                <div className="dv-type">
                  {type}
                  <span>
                    {Number(item.max_marks)} {Number(item.max_marks) === 1 ? "mark" : "marks"}
                  </span>
                </div>
                <button
                  className={"flag " + (item.flagged ? "on" : "")}
                  aria-pressed={item.flagged}
                  disabled={locked}
                  onClick={() => edit({ flagged: !item.flagged })}
                >
                  <i aria-hidden="true" className="dv-bookmark" />
                  {item.flagged ? "Flagged" : "Flag for review"}
                </button>
              </header>
              <h2 className="question" id="delivery-prompt" ref={prompt} tabIndex={-1}>
                {item.prompt}
              </h2>
              <fieldset disabled={locked} aria-labelledby="delivery-prompt">
                <legend className="field-instruction">{instruction}</legend>
                {item.kind === "written" ? (
                  <textarea
                    className="dv-written"
                    aria-label="Your answer"
                    value={item.written_answer}
                    onChange={(e) => edit({ written_answer: e.target.value })}
                  />
                ) : (
                  item.options.map((o, n) => {
                    const checked = item.selected_option_ids.includes(o.id);
                    return (
                      <label key={o.id} className={"option " + (checked ? "chosen" : "")}>
                        <input
                          type={item.kind === "multiple" ? "checkbox" : "radio"}
                          name="delivery-choice"
                          checked={checked}
                          onChange={() =>
                            edit({
                              selected_option_ids:
                                item.kind === "single"
                                  ? [o.id]
                                  : checked
                                    ? item.selected_option_ids.filter((id) => id !== o.id)
                                    : [...item.selected_option_ids, o.id],
                            })
                          }
                        />
                        <span className="dv-option-letter" aria-hidden="true">
                          {n < 26 ? String.fromCharCode(65 + n) : n + 1}
                        </span>
                        <span>{o.label}</span>
                      </label>
                    );
                  })
                )}
              </fieldset>
              {conflict && (
                <section className="dv-conflict" role="alert">
                  <h3>Answer conflict</h3>
                  <div className="dv-versions">
                    {[
                      [conflict, "Server answer"],
                      [item, "Your draft"],
                    ].map(([q, label]) => (
                      <div key={label}>
                        <b>{label}</b>
                        <p>{answerText(q)}</p>
                        <small>{q.flagged ? "Flagged" : "Unflagged"}</small>
                      </div>
                    ))}
                  </div>
                  <div className="row">
                    <button
                      className="primary"
                      disabled={locked}
                      onClick={() => session.resolve(item.slot, true)}
                    >
                      Keep my draft
                    </button>
                    <button
                      className="secondary"
                      disabled={locked}
                      onClick={() => session.resolve(item.slot, false)}
                    >
                      Use server answer
                    </button>
                  </div>
                </section>
              )}
              <div className="dv-save-line">
                <SaveStatus state={status === "Save failed" ? "error" : pendingCount ? "pending" : "saved"}>
                  {status}
                </SaveStatus>
                <button
                  className="quiet"
                  disabled={locked || !answered(item)}
                  onClick={() =>
                    edit(item.kind === "written" ? { written_answer: "" } : { selected_option_ids: [] })
                  }
                >
                  Clear answer
                </button>
              </div>
              <div className="actions">
                <button className="secondary" disabled={!index} onClick={() => go(index - 1)}>
                  Previous
                </button>
                <button
                  className="primary"
                  onClick={() => (index + 1 === items.length ? setReview(true) : go(index + 1))}
                >
                  {index + 1 === items.length ? "Review answers" : "Next question"}
                </button>
              </div>
            </>
          )}
        </article>
        <aside className="dv-rail">
          <section id="delivery-sheet" tabIndex={-1} className="side">
            <div className="side-head">
              <div className="split">
                <h2>Answer sheet</h2>
              </div>
              <div className="progress-top">
                <span>Answered</span>
                <strong>
                  {count} / {items.length}
                </strong>
              </div>
              <div className="track" aria-hidden="true">
                <span style={{ width: (100 * count) / items.length + "%" }} />
              </div>
            </div>
            <div className="side-content">
              <nav className="numbers" aria-label="Questions">
                {items.map((q, n) => (
                  <button
                    key={q.slot}
                    aria-current={!review && index === n ? "step" : undefined}
                    aria-label={`Question ${q.display_no}, ${answered(q) ? "answered" : "unanswered"}${q.flagged ? ", flagged" : ""}`}
                    className={[
                      "number",
                      answered(q) && "answered",
                      !review && index === n && "current",
                      q.flagged && "flagged",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    onClick={() => go(n)}
                  >
                    {String(q.display_no).padStart(2, "0")}
                    {answered(q) && <span aria-hidden="true" className="dv-punch" />}
                  </button>
                ))}
              </nav>
              <div className="dv-tally">
                <span>{items.length - count} unanswered</span>
                <span>{flagged} flagged</span>
              </div>
              <button className="secondary block" onClick={() => setReview(true)}>
                Review answers
              </button>
            </div>
          </section>
          <div className="tools">
            <details>
              <summary>Scratchpad</summary>
              <div className="tool-body">
                <label>
                  Private rough work
                  <textarea
                    key={paper.attempt_id}
                    disabled={locked}
                    defaultValue={record.scratch}
                    onChange={(e) => session.scratch(e.target.value)}
                  />
                </label>
              </div>
            </details>
            <details>
              <summary>Workspace settings</summary>
              <div className="tool-body prefs">
                <label>
                  Text size{" "}
                  <select
                    disabled={prefBusy}
                    value={prefs.font_percent}
                    onChange={(e) => preference({ font_percent: Number(e.target.value) })}
                  >
                    {Array.from({ length: 121 }, (_, i) => 80 + i).map((n) => (
                      <option key={n} value={n}>
                        {n}%
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <input
                    type="checkbox"
                    disabled={prefBusy}
                    checked={prefs.workspace_layout === "focus"}
                    onChange={(e) =>
                      preference({ workspace_layout: e.target.checked ? "focus" : "standard" })
                    }
                  />{" "}
                  Focus layout
                </label>
                {state.preferenceError && <p role="alert">{state.preferenceError}</p>}
              </div>
            </details>
          </div>
        </aside>
      </div>
    </main>
  );
}

function LiveAttempt({ accountId, attemptId }) {
  const [state, setState] = useState({});
  const [session, setSession] = useState(null);
  useEffect(() => {
    const model = new AttemptSession(accountId, attemptId, setState);
    setSession(model);
    const logout = (id) => {
      if (id !== accountId) return;
      model.active = false;
      model.record = undefined;
      setState({ denied: true, error: "You have signed out." });
    };
    const localLogout = (e) => logout(e.detail);
    const channel =
      typeof BroadcastChannel === "function" ? new BroadcastChannel("folio-delivery-logout") : null;
    if (channel) channel.onmessage = (e) => logout(e.data);
    window.addEventListener("folio-delivery-logout", localLogout);
    let timer;
    let retryDelay = 1000;
    function schedule() {
      clearTimeout(timer);
      if (!model.active || model.closed || model.state.denied) return;
      let delay = 15000;
      if (!navigator.onLine) {
        // A local check also catches a missed online event after an offline reload.
        delay = retryDelay = 1000;
      } else if (model.state.error && (!model.record || model.record.pending.length)) {
        delay = retryDelay;
        retryDelay = Math.min(retryDelay * 2, 15000);
      } else {
        retryDelay = 1000;
      }
      timer = setTimeout(poll, delay);
    }
    async function poll() {
      if (navigator.onLine) await model.refresh();
      schedule();
    }
    const reconnect = () => {
      clearTimeout(timer);
      retryDelay = 1000;
      poll();
    };
    model.init().then(schedule);
    window.addEventListener("online", reconnect);
    window.addEventListener("offline", schedule);
    return () => {
      model.active = false;
      clearTimeout(timer);
      channel?.close();
      window.removeEventListener("folio-delivery-logout", localLogout);
      window.removeEventListener("online", reconnect);
      window.removeEventListener("offline", schedule);
    };
  }, [accountId, attemptId]);
  return session && <AttemptView state={state} session={session} />;
}

export function CandidateAttempt(props) {
  return <LiveAttempt key={JSON.stringify([props.accountId, props.attemptId])} {...props} />;
}
