import { MarkChips, RedPenMark } from "../components/instruments.jsx";
import { markingProgress, markSteps, scriptLabels } from "../domain/visuals.js";
import React, { useCallback, useEffect, useMemo, useState } from "react";

const BLIND_KEY = "folio.results.blindMarking";
const readBlind = () => { try { return localStorage.getItem(BLIND_KEY) === "on"; } catch { return false; } };
import {
  Banner,
  EmptyPanel,
  ExamStatusPill,
  ExaminerTabs,
  PageHead,
  SaveStatus,
  StatusPill,
} from "../components/primitives.jsx";
import { formatDateTime, formatMarks, validateAwardInput } from "../domain/rules.js";

function WrittenResponseCard({ api, item, frozen, onGraded, blind = false, scriptLabel = "" }) {
  const [draft, setDraft] = useState(item.awarded_marks ?? "");
  const [issue, setIssue] = useState(null);
  const [saveState, setSaveState] = useState("idle");

  useEffect(() => {
    setDraft(item.awarded_marks ?? "");
  }, [item.awarded_marks]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (frozen) return;
    const check = validateAwardInput(draft, item.max_marks);
    if (check.issue) {
      setIssue(check.issue);
      setSaveState("error");
      return;
    }
    setIssue(null);
    setSaveState("saving");
    try {
      const updated = await api.gradeWrittenItem(item.attempt_id, item.slot, check.value);
      setDraft(updated.awarded_marks);
      setSaveState("saved");
      onGraded(updated);
    } catch (err) {
      setIssue(err.issues?.[0] ?? { code: err.code, message: err.message });
      setSaveState("error");
    }
  }

  const inputId = `award-${item.attempt_id}-${item.slot}`;
  const isBlank = !item.written_answer || !item.written_answer.trim();

  return (
    <article className="sheet" id={`script-${item.attempt_id}-${item.slot}`} aria-labelledby={`title-${item.attempt_id}-${item.slot}`}>
      <div className="folio-line">
        <span className="qno">
          Slot {String(item.slot).padStart(2, "0")} · Display #{item.display_no} · {item.topic}
        </span>
        {item.awarded_marks !== null ? (
          <StatusPill
            tone="sage"
            glyph="✓"
            label={`Awarded ${formatMarks(item.awarded_marks)} / ${formatMarks(item.max_marks)}`}
          />
        ) : (
          <StatusPill tone="amber" glyph="◷" label={`Pending · max ${formatMarks(item.max_marks)}`} />
        )}
      </div>

      <h3 className="question" id={`title-${item.attempt_id}-${item.slot}`}>
        {item.prompt}
      </h3>

      {blind ? (
        <p className="res-muted res-blind-id"><strong>{scriptLabel}</strong> · identity hidden for fair marking</p>
      ) : (
        <p className="res-muted">
          Candidate: <strong>{item.candidate_name}</strong> ({item.candidate_email}) · Finalized{" "}
          {formatDateTime(item.finalized_at)} ({item.close_reason})
        </p>
      )}

      {item.rubric && (
        <div className="res-rubric">
          <span className="mini">Examiner rubric (private)</span>
          <div>{item.rubric}</div>
        </div>
      )}

      <div className="res-answer-box res-script" aria-label="Candidate written response">
        <RedPenMark awarded={item.awarded_marks} cap={item.max_marks} />
        {isBlank ? <span className="res-muted">Blank response (auto-scored 0.00 at finalization).</span> : item.written_answer}
      </div>

      <form onSubmit={handleSubmit} noValidate>
        <div className="res-inline-actions">
          <div className="res-field" style={{ marginBottom: 0, minWidth: 210 }}>
            <label htmlFor={inputId}>Awarded marks (0.00 – {formatMarks(item.max_marks)})</label>
            <input
              id={inputId}
              className="res-input"
              type="text"
              inputMode="decimal"
              disabled={frozen || saveState === "saving"}
              value={draft}
              aria-invalid={issue ? true : undefined}
              aria-describedby={issue ? `${inputId}-err` : undefined}
              onChange={e => {
                setDraft(e.target.value);
                if (issue) setIssue(null);
                if (saveState !== "idle") setSaveState("idle");
              }}
            />
          </div>

          <button type="submit" className="primary" disabled={frozen || saveState === "saving"} style={{ alignSelf: "flex-end" }}>
            {frozen ? "Grades frozen" : "Save award"}
          </button>

          <div style={{ alignSelf: "flex-end" }}>
            {saveState === "saving" && <SaveStatus state="pending">Saving…</SaveStatus>}
            {saveState === "saved" && (
              <SaveStatus state="saved">
                {api.mode === "preview" ? "Saved in preview" : "Saved on server"}
              </SaveStatus>
            )}
            {saveState === "error" && <SaveStatus state="error">Save failed</SaveStatus>}
          </div>
        </div>

        <MarkChips steps={markSteps(item.max_marks)} value={draft} disabled={frozen || saveState === "saving"}
          onPick={v => { setDraft(v); setIssue(null); setSaveState("idle"); }} />

        {issue && (
          <p id={`${inputId}-err`} className="res-field-error" role="alert" style={{ marginTop: 8 }}>
            {issue.message}
          </p>
        )}
      </form>
    </article>
  );
}

export default function MarkingPage({ api, params, navigate }) {
  const examId = params?.id;
  const [queue, setQueue] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterPending, setFilterPending] = useState(false);
  const [blind, setBlind] = useState(readBlind);
  const chooseBlind = on => { setBlind(on); try { localStorage.setItem(BLIND_KEY, on ? "on" : "off"); } catch { /* storage may be blocked */ } };
  const labels = useMemo(() => scriptLabels(queue?.items ?? []), [queue]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const q = await api.getMarkingQueue(examId);
      setQueue(q);
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [api, examId]);

  useEffect(() => {
    load();
  }, [load]);

  function handleGraded(updated) {
    setQueue(prev => {
      if (!prev) return prev;
      const items = prev.items.map(it =>
        it.attempt_id === updated.attempt_id && it.slot === updated.slot
          ? { ...it, awarded_marks: updated.awarded_marks, graded_by: updated.graded_by }
          : it
      );
      const pending = items.filter(it => it.awarded_marks === null).length;
      return {
        ...prev,
        items,
        pending_written_count: pending,
        graded_written_count: items.length - pending,
      };
    });
  }

  if (loading && !queue) {
    return (
      <main className="shell">
        <PageHead crumb="Examiner workspace" title="Written marking" details={<span>Loading…</span>} />
        <section className="board" role="status">Loading written responses…</section>
      </main>
    );
  }

  if (error && !queue) {
    return (
      <main className="shell">
        <PageHead crumb="Examiner workspace" title="Written marking" details={<span>Unavailable</span>} />
        <Banner tone="rust" title="Unable to load marking queue" role="alert">
          <p>{error.message}</p>
        </Banner>
      </main>
    );
  }

  const frozen = Boolean(queue.results_published_at);
  const filtered = filterPending ? queue.items.filter(it => it.awarded_marks === null) : queue.items;
  // In blind mode, order by script label so position cannot hint at who finished when.
  const visible = blind ? [...filtered].sort((a, b) => labels.get(a.attempt_id).localeCompare(labels.get(b.attempt_id)) || a.slot - b.slot) : filtered;
  const progress = markingProgress(queue.items);
  const nextUnmarked = visible.find(it => it.awarded_marks === null);
  function goToNextUnmarked() {
    if (!nextUnmarked) return;
    document.getElementById(`script-${nextUnmarked.attempt_id}-${nextUnmarked.slot}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    document.getElementById(`award-${nextUnmarked.attempt_id}-${nextUnmarked.slot}`)?.focus({ preventScroll: true });
  }

  return (
    <main className="shell">
      <PageHead
        crumb="Examiner workspace"
        title="Written marking"
        details={
          <>
            <b>{queue.exam_title}</b>
            <i />
            <ExamStatusPill status={queue.status} />
          </>
        }
      />

      <ExaminerTabs examId={examId} active="marking" navigate={navigate} />

      {frozen && (
        <Banner tone="sage" title="Results released — awards frozen">
          <p>Results were published on {formatDateTime(queue.results_published_at)}. Marks can no longer be modified.</p>
        </Banner>
      )}

      {queue.unfinalized_attempts > 0 && (
        <Banner tone="amber" title="Open attempts still running">
          <p>{queue.unfinalized_attempts} real attempt(s) are not yet finalized and are excluded from grading until closed.</p>
        </Banner>
      )}

      <section className="board" style={{ marginBottom: 18 }}>
        <div className="split">
          <h2>Marking summary</h2>
          <div className="row res-marking-switches">
          <label className="res-switch">
            <input type="checkbox" checked={blind} onChange={e => chooseBlind(e.target.checked)} />
            <span>Blind marking</span>
          </label>
          <label className="row" style={{ fontSize: 13 }}>
            <input
              type="checkbox"
              checked={filterPending}
              onChange={e => setFilterPending(e.target.checked)}
            />
            Pending only ({queue.pending_written_count})
          </label>
          </div>
        </div>
        {blind && <p className="res-muted res-blind-note">Names, emails and finish times are hidden while you mark, and scripts are ordered by label. Awards are still stored against the right attempt.</p>}
        <div className="res-marking-progress">
          <span><b className="res-mono">{progress.done}</b> of <b className="res-mono">{progress.total}</b> {progress.total === 1 ? "script" : "scripts"} marked</span>
          <span className="res-marking-progress__rule" aria-hidden="true">
            {queue.items.map((it, n) => <i key={n} className={it.awarded_marks !== null ? "on" : ""} />)}
          </span>
          <button type="button" className="secondary" disabled={!nextUnmarked || frozen} onClick={goToNextUnmarked}>
            {nextUnmarked ? "Next unmarked →" : "All marked ✓"}
          </button>
        </div>
        <div className="summary-grid" style={{ marginBottom: 0 }}>
          <div className="stat">
            <span className="mini">Pending written</span>
            <strong>{queue.pending_written_count}</strong>
          </div>
          <div className="stat">
            <span className="mini">Graded written</span>
            <strong>{queue.graded_written_count}</strong>
          </div>
          <div className="stat">
            <span className="mini">Open attempts</span>
            <strong>{queue.unfinalized_attempts}</strong>
          </div>
        </div>
      </section>

      {visible.length === 0 ? (
        <section className="board">
          <EmptyPanel
            title={filterPending ? "No pending written responses" : "No finalized written responses"}
            detail={
              filterPending
                ? "All finalized written responses have been scored."
                : "Written responses appear here once candidates finalize their attempts."
            }
          />
        </section>
      ) : (
        <div className="res-stack">
          {visible.map(item => (
            <WrittenResponseCard
              key={`${item.attempt_id}-${item.slot}`}
              api={api}
              item={item}
              frozen={frozen}
              onGraded={handleGraded}
              blind={blind}
              scriptLabel={labels.get(item.attempt_id)}
            />
          ))}
        </div>
      )}
    </main>
  );
}
