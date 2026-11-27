import React, { useCallback, useEffect, useState } from "react";
import {
  Banner,
  EmptyPanel,
  ExamStatusPill,
  ExaminerTabs,
  PageHead,
  StatusPill,
  triggerPdfDownload,
} from "../components/primitives.jsx";
import { formatDateTime, formatMarks } from "../domain/rules.js";

export default function ResultsPage({ api, params, navigate }) {
  const examId = params?.id;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [publishing, setPublishing] = useState(false);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getExamResults(examId);
      setData(res);
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

  async function handlePublish() {
    setActionError(null);
    setPublishing(true);
    try {
      const updated = await api.publishResults(examId);
      setData(updated);
    } catch (err) {
      setActionError(err);
    } finally {
      setPublishing(false);
    }
  }

  async function handleDownloadClassPdf() {
    setActionError(null);
    setExporting(true);
    try {
      const dl = await api.downloadClassReport(examId);
      triggerPdfDownload(dl);
    } catch (err) {
      setActionError(err);
    } finally {
      setExporting(false);
    }
  }

  if (loading && !data) {
    return (
      <main className="shell">
        <PageHead crumb="Examiner workspace" title="Results & analytics" details={<span>Loading…</span>} />
        <section className="board" role="status">Loading exam results…</section>
      </main>
    );
  }

  if (error && !data) {
    return (
      <main className="shell">
        <PageHead crumb="Examiner workspace" title="Results & analytics" details={<span>Unavailable</span>} />
        <Banner tone="rust" title="Unable to load results" role="alert">
          <p>{error.message}</p>
        </Banner>
      </main>
    );
  }

  const s = data.summary;

  return (
    <main className="shell">
      <PageHead
        crumb="Examiner workspace"
        title="Results & analytics"
        details={
          <>
            <b>{data.exam_title}</b>
            <i />
            <ExamStatusPill status={data.status} />
            <i />
            <span>Total {data.total_marks} marks</span>
          </>
        }
        aside={
          <div className="res-inline-actions">
            <button type="button" className="secondary" disabled={exporting} onClick={handleDownloadClassPdf}>
              {exporting ? "Generating PDF…" : "Download class PDF"}
            </button>
            {!data.results_published_at && (
              <button
                type="button"
                className="primary"
                disabled={!data.can_release || publishing}
                onClick={handlePublish}
              >
                {publishing ? "Releasing…" : "Publish results"}
              </button>
            )}
          </div>
        }
      />

      <ExaminerTabs examId={examId} active="results" navigate={navigate} />

      {actionError && (
        <Banner tone="rust" title="Action refused" role="alert">
          <p>{actionError.message}</p>
        </Banner>
      )}

      {data.results_published_at ? (
        <Banner tone="sage" title="Results released and issued">
          <p>
            Released on {formatDateTime(data.results_published_at)}. Candidate scores are frozen and verifiable PDF reports have been issued.
          </p>
        </Banner>
      ) : data.release_blockers.length > 0 ? (
        <Banner tone="amber" title="Release gate locked">
          <ul>
            {data.release_blockers.map((b, idx) => (
              <li key={idx}>{b.message}</li>
            ))}
          </ul>
        </Banner>
      ) : (
        <Banner tone="sage" title="Ready to release">
          <p>All real attempts are finalized and graded after close. Publishing freezes awards and issues verifiable candidate PDFs.</p>
        </Banner>
      )}

      <section className="board" style={{ marginBottom: 20 }}>
        <h2>Class summary</h2>
        <p className="res-muted">
          Based on real finalized attempts only (excludes sandbox previews and {s.no_show_count} no-show enrollment{s.no_show_count === 1 ? "" : "s"}).
        </p>

        <div className="res-cards-grid">
          <div className="stat">
            <span className="mini">Enrolled / Finalized</span>
            <strong>{s.finalized_count} / {s.enrolled_count}</strong>
          </div>
          <div className="stat">
            <span className="mini">Graded attempts</span>
            <strong>{s.graded_attempt_count} / {s.finalized_count}</strong>
          </div>
          <div className="stat">
            <span className="mini">Mean score</span>
            <strong>{s.mean_score !== null ? s.mean_score : "No data"}</strong>
          </div>
          <div className="stat">
            <span className="mini">Median / Range</span>
            <strong>
              {s.median_score !== null ? `${s.median_score} (${s.min_score}–${s.max_score})` : "No data"}
            </strong>
          </div>
        </div>

        <h3>Candidate score register</h3>
        {data.attempts.length === 0 ? (
          <EmptyPanel
            title="No finalized real attempts"
            detail="Candidate scores appear here once enrolled candidates finalize attempts."
          />
        ) : (
          <div className="res-table-wrap">
            <table className="data-table res-responsive-table">
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Close</th>
                  <th>Graded items</th>
                  <th>Score</th>
                  <th>Status</th>
                  <th>Verification code</th>
                </tr>
              </thead>
              <tbody>
                {data.attempts.map(row => (
                  <tr key={row.attempt_id}>
                    <td data-label="Candidate">
                      <div>{row.display_name}</div>
                      <div className="res-muted">{row.email}</div>
                    </td>
                    <td data-label="Close">{row.close_reason}</td>
                    <td data-label="Graded items" className="res-mono">
                      {row.graded_count} / {row.item_count}
                    </td>
                    <td data-label="Score" className="res-mono">
                      {row.total_score !== null ? `${row.total_score} / ${row.max_marks}` : "Pending"}
                    </td>
                    <td data-label="Status">
                      <StatusPill
                        tone={row.status === "pending_grade" ? "amber" : "sage"}
                        glyph={row.status === "pending_grade" ? "◷" : "✓"}
                        label={row.status === "released" ? "Released" : row.status === "graded" ? "Graded" : "Pending"}
                      />
                    </td>
                    <td data-label="Verification code" className="res-mono">
                      {row.verification_code ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="board">
        <h2>Question analytics</h2>
        <p className="res-muted">
          Observed facility averages awarded marks divided by item cap across graded exposures. Empty groups display “No data”.
        </p>

        {data.question_analytics.length === 0 ? (
          <EmptyPanel title="No questions assigned" detail="Assign published items to review question statistics." />
        ) : (
          <div className="res-table-wrap">
            <table className="data-table res-responsive-table">
              <thead>
                <tr>
                  <th>Slot & Version</th>
                  <th>Topic & Kind</th>
                  <th>Exposures</th>
                  <th>Skipped</th>
                  <th>Observed facility</th>
                  <th>Common incorrect selections</th>
                </tr>
              </thead>
              <tbody>
                {data.question_analytics.map(q => (
                  <tr key={`${q.slot}-${q.version_id}`}>
                    <td data-label="Slot & Version">
                      <div className="res-mono">Slot {String(q.slot).padStart(2, "0")} · v{q.version_no}</div>
                      <div>{q.prompt}</div>
                    </td>
                    <td data-label="Topic & Kind">
                      <div>{q.topic}</div>
                      <div className="res-muted">{q.kind} · {formatMarks(q.max_marks)} marks</div>
                    </td>
                    <td data-label="Exposures" className="res-mono">{q.exposure_count}</td>
                    <td data-label="Skipped" className="res-mono">{q.skip_rate_display}</td>
                    <td data-label="Observed facility" className="res-mono">
                      {q.facility_display}
                      {q.graded_exposure_count > 0 ? ` (${q.graded_exposure_count} graded)` : ""}
                    </td>
                    <td data-label="Common incorrect">
                      {q.common_incorrect_selections.length === 0 ? (
                        <span className="res-muted">{q.exposure_count === 0 ? "No data" : "None"}</span>
                      ) : (
                        q.common_incorrect_selections.map(w => (
                          <div key={w.option_no}>
                            {w.label} <span className="res-mono">({w.count}/{w.exposure_count})</span>
                          </div>
                        ))
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
