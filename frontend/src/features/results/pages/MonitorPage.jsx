import React, { useCallback, useEffect, useState } from "react";
import {
  AttemptStatusBadge,
  Banner,
  EmptyPanel,
  ExamStatusPill,
  ExaminerTabs,
  PageHead,
  SaveStatus,
} from "../components/primitives.jsx";
import {
  MAX_ANNOUNCEMENT_LEN,
  STALE_FEED_MS,
  formatTime,
  isFeedStale,
  validateAnnouncementInput,
} from "../domain/rules.js";

function two(n) {
  return String(n).padStart(2, "0");
}

export default function MonitorPage({ api, params, navigate, pollMs = 8000 }) {
  const examId = params?.id;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastSyncMs, setLastSyncMs] = useState(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [syncError, setSyncError] = useState(null);

  const [message, setMessage] = useState("");
  const [formIssue, setFormIssue] = useState(null);
  const [postState, setPostState] = useState("idle");

  const load = useCallback(async ({ background = false } = {}) => {
    if (!background) setLoading(true);
    try {
      const snap = await api.getMonitor(examId);
      setData(snap);
      setError(null);
      setSyncError(null);
      setLastSyncMs(Date.now());
    } catch (err) {
      if (!background || !data) {
        setError(err);
      } else {
        setSyncError(err);
      }
    } finally {
      if (!background) setLoading(false);
    }
  }, [api, examId, data]);

  useEffect(() => {
    load({ background: false });
  }, [examId, api]);

  useEffect(() => {
    if (!pollMs) return undefined;
    const pollId = setInterval(() => load({ background: true }), pollMs);
    const tickId = setInterval(() => setNowMs(Date.now()), 5000);
    return () => {
      clearInterval(pollId);
      clearInterval(tickId);
    };
  }, [load, pollMs]);

  const stale = Boolean(syncError) || isFeedStale(lastSyncMs, nowMs, STALE_FEED_MS);

  async function handlePost(e) {
    e.preventDefault();
    const check = validateAnnouncementInput(message);
    if (check.issue) {
      setFormIssue(check.issue);
      return;
    }
    setFormIssue(null);
    setPostState("saving");
    try {
      const created = await api.postAnnouncement(examId, check.value);
      setData(prev => (prev ? { ...prev, announcements: [created, ...prev.announcements] } : prev));
      setMessage("");
      setPostState("saved");
    } catch (err) {
      setFormIssue(err.issues?.[0] ?? { code: err.code, message: err.message });
      setPostState("error");
    }
  }

  if (loading && !data) {
    return (
      <main className="shell">
        <PageHead crumb="Examiner workspace" title="Examination monitor" details={<span>Loading monitor…</span>} />
        <section className="board" role="status">Loading exam monitor…</section>
      </main>
    );
  }

  if (error && !data) {
    return (
      <main className="shell">
        <PageHead crumb="Examiner workspace" title="Examination monitor" details={<span>Unavailable</span>} />
        <Banner tone="rust" title="Unable to load examination monitor" role="alert">
          <p>{error.message}</p>
        </Banner>
      </main>
    );
  }

  return (
    <main className="shell">
      <PageHead
        crumb="Examiner workspace"
        title="Examination monitor"
        details={
          <>
            <b>{data.exam_title}</b>
            <i />
            <ExamStatusPill status={data.status} />
            <i />
            <span>{data.total_items} questions</span>
          </>
        }
        aside={
          <div className="clock">
            <span className="clock-label">Server sync</span>
            <strong>{formatTime(data.server_time)}</strong>
          </div>
        }
      />

      <ExaminerTabs examId={examId} active="monitor" navigate={navigate} />

      {stale && (
        <Banner tone="amber" title="Monitor feed may be stale" role="status">
          <p>
            {syncError
              ? `Last refresh failed: ${syncError.message}`
              : "More than 30 seconds have passed since the last confirmed server update."}
          </p>
          <p style={{ marginTop: 8 }}>
            <button type="button" className="secondary" onClick={() => load({ background: false })}>
              Refresh monitor now
            </button>
          </p>
        </Banner>
      )}

      <div className="workgrid">
        <section className="board" aria-labelledby="monitor-roster-heading">
          <div className="split">
            <h2 id="monitor-roster-heading">Candidate register</h2>
            <button type="button" className="quiet" onClick={() => load({ background: false })}>
              Refresh
            </button>
          </div>

          <div className="summary-grid">
            <div className="stat">
              <span className="mini">Enrolled</span>
              <strong>{two(data.counts.enrolled)}</strong>
            </div>
            <div className="stat">
              <span className="mini">In progress</span>
              <strong>{two(data.counts.in_progress)}</strong>
            </div>
            <div className="stat">
              <span className="mini">Finalized</span>
              <strong>{two(data.counts.finalized)}</strong>
            </div>
          </div>

          {data.roster.length === 0 ? (
            <EmptyPanel
              title="No enrolled candidates yet"
              detail="Enrolled candidates and live attempt progress appear here once candidates are assigned."
            />
          ) : (
            <div className="res-table-wrap">
              <table className="data-table res-responsive-table">
                <thead>
                  <tr>
                    <th>Candidate</th>
                    <th>Answered</th>
                    <th>Attempt</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {data.roster.map(row => (
                    <tr key={row.candidate_id}>
                      <td data-label="Candidate">
                        <div>{row.display_name}</div>
                        <div className="res-muted">{row.email}</div>
                      </td>
                      <td data-label="Answered">
                        <span className="res-mono">
                          {row.answered_count} / {row.total_items}
                        </span>
                      </td>
                      <td data-label="Attempt">
                        <AttemptStatusBadge status={row.status} />
                      </td>
                      <td data-label="Notes">
                        {row.incident_count > 0 ? (
                          <span className="res-muted">
                            {row.incident_count} reconnect/incident observation{row.incident_count > 1 ? "s" : ""} (no penalty)
                          </span>
                        ) : (
                          <span className="res-muted">
                            {row.last_saved_at ? `Saved ${formatTime(row.last_saved_at)}` : "No saves yet"}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="res-neutral-note">
            Reconnect and incident entries are neutral timeline observations for examiner review and apply zero automatic penalty.
          </p>
        </section>

        <aside className="side" aria-label="Exam activity and announcements">
          <div className="side-head">
            <h2>Exam activity</h2>
          </div>
          <div className="side-content">
            <form onSubmit={handlePost} noValidate>
              <div className="res-field">
                <label htmlFor="announcement-input">Announcement to enrolled candidates</label>
                <textarea
                  id="announcement-input"
                  value={message}
                  maxLength={MAX_ANNOUNCEMENT_LEN}
                  aria-invalid={formIssue ? true : undefined}
                  aria-describedby={formIssue ? "announcement-error" : "announcement-hint"}
                  onChange={e => {
                    setMessage(e.target.value);
                    if (formIssue) setFormIssue(null);
                    if (postState !== "idle") setPostState("idle");
                  }}
                />
                <span id="announcement-hint" className="res-muted">
                  {message.trim().length} / {MAX_ANNOUNCEMENT_LEN} characters
                </span>
                {formIssue && (
                  <span id="announcement-error" className="res-field-error" role="alert">
                    {formIssue.message}
                  </span>
                )}
              </div>

              <div className="res-inline-actions">
                <button type="submit" className="primary" disabled={postState === "saving"}>
                  {api.mode === "preview" ? "Post to preview" : "Send announcement"}
                </button>
                {postState === "saving" && <SaveStatus state="pending">Sending…</SaveStatus>}
                {postState === "saved" && (
                  <SaveStatus state="saved">
                    {api.mode === "preview" ? "Saved in preview" : "Saved on server"}
                  </SaveStatus>
                )}
                {postState === "error" && <SaveStatus state="error">Save failed</SaveStatus>}
              </div>
            </form>

            {data.announcements.length === 0 && data.incidents.length === 0 ? (
              <EmptyPanel
                title="No activity recorded yet"
                detail="Candidate start/reconnect observations and posted announcements will appear here."
              />
            ) : (
              <>
                {data.announcements.map(ann => (
                  <div className="event" key={ann.id}>
                    <time>
                      {api.mode === "preview" ? "Preview announcement" : "Announcement"} · {formatTime(ann.posted_at)}
                    </time>
                    <div>{ann.message}</div>
                  </div>
                ))}
                {data.incidents.map(ev => (
                  <div className="event" key={ev.id}>
                    <time>
                      {formatTime(ev.recorded_at)} · {ev.kind} (observation)
                    </time>
                    <div>
                      <strong>{ev.candidate_name}</strong>
                      {ev.note ? ` — ${ev.note}` : ""}
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </aside>
      </div>
    </main>
  );
}
