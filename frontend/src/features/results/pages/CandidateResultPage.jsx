import React, { useEffect, useState } from "react";
import {
  Banner,
  PageHead,
  StatusPill,
  triggerPdfDownload,
} from "../components/primitives.jsx";
import { formatDateTime } from "../domain/rules.js";
import { paths } from "../paths.js";

export default function CandidateResultPage({ api, params, navigate }) {
  const attemptId = params?.id;
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadErr, setDownloadErr] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    api
      .getCandidateResult(attemptId)
      .then(res => {
        if (active) setResult(res);
      })
      .catch(err => {
        if (active) setError(err);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [api, attemptId]);

  async function handleDownload() {
    setDownloadErr(null);
    setDownloading(true);
    try {
      const dl = await api.downloadCandidateReport(attemptId);
      triggerPdfDownload(dl);
    } catch (err) {
      setDownloadErr(err.message);
    } finally {
      setDownloading(false);
    }
  }

  async function handleCopyCode() {
    if (!result?.verification_code || !navigator.clipboard) return;
    await navigator.clipboard.writeText(result.verification_code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (loading) {
    return (
      <main className="shell">
        <PageHead crumb="Candidate results" title="Released result" details={<span>Loading…</span>} />
        <section className="board" role="status">Loading your released result…</section>
      </main>
    );
  }

  if (error) {
    const isNotAvailable = error.status === 404 || error.status === 403 || error.status === 401;
    return (
      <main className="shell">
        <PageHead crumb="Candidate results" title="Released result" details={<span>Restricted</span>} />
        <Banner
          tone={isNotAvailable ? "amber" : "rust"}
          title={isNotAvailable ? "Result unavailable or not yet released" : "Unable to load result"}
          role="alert"
        >
          <p>
            {isNotAvailable
              ? "Results are visible only to the owning candidate after the examination closes and the examiner releases grades."
              : error.message}
          </p>
        </Banner>
      </main>
    );
  }

  return (
    <main className="shell">
      <PageHead
        crumb="Candidate results"
        title={result.exam_title}
        details={
          <>
            <b>{result.candidate_name}</b>
            <i />
            <span>Finalized {formatDateTime(result.finalized_at)}</span>
            <i />
            <span>Released {formatDateTime(result.results_published_at)}</span>
          </>
        }
        aside={
          <button type="button" className="primary" disabled={downloading} onClick={handleDownload}>
            {downloading ? "Downloading…" : "Download official PDF"}
          </button>
        }
      />

      {downloadErr && (
        <Banner tone="rust" title="Download failed" role="alert">
          <p>{downloadErr}</p>
        </Banner>
      )}

      <section className="board" style={{ marginBottom: 20 }}>
        <div className="res-score-hero">
          <div>
            <span className="mini">Released official score</span>
            <div>
              <strong>{result.total_score}</strong>{" "}
              <span className="res-muted">/ {result.max_marks} marks</span>
            </div>
          </div>
          <StatusPill tone="sage" glyph="✓" label={`Closed (${result.close_reason})`} />
        </div>

        <div className="res-rubric">
          <span className="mini">Report authenticity record</span>
          <p style={{ margin: "6px 0" }}>
            Verification code: <code className="res-mono">{result.verification_code}</code>{" "}
            <button type="button" className="quiet" onClick={handleCopyCode}>
              {copied ? "Copied" : "Copy code"}
            </button>
          </p>
          <p className="res-muted">
            PDF SHA-256: <code className="res-mono">{result.sha256_hex}</code>
          </p>
          <p style={{ marginTop: 8 }}>
            <a
              href={"#" + paths.verify}
              className="quiet"
              onClick={e => {
                if (!navigate) return;
                e.preventDefault();
                navigate(paths.verify);
              }}
            >
              Verify report authenticity →
            </a>
          </p>
        </div>
      </section>

      <div className="res-stack">
        {result.items.map(item => (
          <article className="sheet" key={item.slot}>
            <div className="folio-line">
              <span className="qno">
                Question {String(item.display_no).padStart(2, "0")} · {item.kind}
              </span>
              <StatusPill
                tone="sage"
                label={`${item.awarded_marks} / ${item.max_marks} marks`}
              />
            </div>
            <h2 className="question">{item.prompt}</h2>
            {item.kind === "written" ? (
              <div className="res-answer-box">
                {item.written_answer?.trim() ? item.written_answer : <span className="res-muted">No written response submitted.</span>}
              </div>
            ) : item.selected_options.length === 0 ? (
              <p className="res-muted">No option selected.</p>
            ) : (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {item.selected_options.map(opt => (
                  <li key={opt.option_no}>{opt.label}</li>
                ))}
              </ul>
            )}
          </article>
        ))}
      </div>
    </main>
  );
}
