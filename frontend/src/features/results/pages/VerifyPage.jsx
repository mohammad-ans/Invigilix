import React, { useState } from "react";
import { Banner, PageHead, StatusPill } from "../components/primitives.jsx";
import { isPdfBytes, sha256HexFromBuffer, validateVerifyInputs } from "../domain/rules.js";

export default function VerifyPage({ api }) {
  const [code, setCode] = useState("");
  const [digest, setDigest] = useState("");
  const [fileName, setFileName] = useState("");
  const [status, setStatus] = useState("empty"); // empty | invalid-file | pending | valid | invalid | error
  const [issues, setIssues] = useState([]);
  const [errorMsg, setErrorMsg] = useState("");

  async function handleFileChange(e) {
    const file = e.target.files?.[0];
    setIssues([]);
    setErrorMsg("");
    if (!file) {
      setFileName("");
      setStatus("empty");
      return;
    }
    setFileName(file.name);
    const buffer = await file.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    if (bytes.length === 0 || !isPdfBytes(bytes)) {
      setDigest("");
      setStatus("invalid-file");
      return;
    }
    const hex = await sha256HexFromBuffer(buffer);
    setDigest(hex);
    setStatus("empty");
  }

  async function handleVerify(e) {
    e.preventDefault();
    setIssues([]);
    setErrorMsg("");
    const check = validateVerifyInputs(code, digest);
    if (check.issues) {
      setIssues(check.issues);
      setStatus("error");
      return;
    }
    setStatus("pending");
    try {
      const res = await api.verifyReport(check.code, check.digest);
      setStatus(res.valid ? "valid" : "invalid");
    } catch (err) {
      if (err.issues?.length) setIssues(err.issues);
      setErrorMsg(err.message);
      setStatus("error");
    }
  }

  const codeIssue = issues.find(i => i.field === "verification_code");
  const digestIssue = issues.find(i => i.field === "sha256_hex");

  return (
    <main className="shell">
      <PageHead
        crumb="Public verification"
        title="Verify issued report"
        details={<span>Confirm report authenticity without revealing candidate, exam, or score details</span>}
      />

      <section className="board" style={{ maxWidth: 680 }}>
        <h2>Report authenticity check</h2>
        <p className="res-muted" style={{ marginBottom: 16 }}>
          Select the downloaded PDF report (computed locally in your browser) or paste its SHA-256 digest together with the verification code printed on the report.
        </p>

        {status === "empty" && !fileName && (
          <Banner tone="sage" title="Ready to verify">
            <p>Provide both a verification code and either a PDF file or its 64-character SHA-256 digest.</p>
          </Banner>
        )}

        {status === "invalid-file" && (
          <Banner tone="rust" title="Invalid PDF file" role="alert">
            <p>
              <strong>{fileName}</strong> is empty or does not have a valid PDF header (%PDF-). Select an unmodified Folio PDF report.
            </p>
          </Banner>
        )}

        {status === "pending" && (
          <Banner tone="amber" title="Verifying authenticity…">
            <p>Checking verification code and SHA-256 digest against the authoritative registry.</p>
          </Banner>
        )}

        {status === "valid" && (
          <Banner tone="sage" title="Valid authentic Folio report" role="status">
            <p>
              <StatusPill tone="sage" glyph="✓" label="Valid" /> The report bytes and verification code match an issued Folio record. No candidate, exam, or score details are disclosed by this service.
            </p>
          </Banner>
        )}

        {status === "invalid" && (
          <Banner tone="rust" title="Report verification failed" role="alert">
            <p>
              <StatusPill tone="rust" glyph="✕" label="Not valid" /> The verification code and SHA-256 digest do not match any issued report. The file may have been altered or the code is incorrect.
            </p>
          </Banner>
        )}

        {status === "error" && (
          <Banner tone="rust" title="Verification could not be completed" role="alert">
            <p>{errorMsg || "Check the highlighted fields below."}</p>
          </Banner>
        )}

        <form onSubmit={handleVerify} noValidate>
          <div className="res-field">
            <label htmlFor="verify-code">Verification code</label>
            <input
              id="verify-code"
              className="res-input res-mono"
              type="text"
              placeholder="e.g. FOL-..."
              value={code}
              aria-invalid={codeIssue ? true : undefined}
              aria-describedby={codeIssue ? "verify-code-err" : undefined}
              onChange={e => {
                setCode(e.target.value);
                if (status === "valid" || status === "invalid") setStatus("empty");
              }}
            />
            {codeIssue && (
              <span id="verify-code-err" className="res-field-error" role="alert">
                {codeIssue.message}
              </span>
            )}
          </div>

          <div className="res-field">
            <label htmlFor="verify-file" className="res-dropzone">
              <strong>Choose downloaded PDF file</strong>
              <div className="res-muted">
                {fileName
                  ? `Selected: ${fileName}`
                  : "PDF bytes stay on this device; only the SHA-256 hash is submitted."}
              </div>
              <input
                id="verify-file"
                type="file"
                accept=".pdf,application/pdf"
                onChange={handleFileChange}
                style={{ marginTop: 8 }}
              />
            </label>
          </div>

          <div className="res-field">
            <label htmlFor="verify-digest">SHA-256 digest (64 hex characters)</label>
            <input
              id="verify-digest"
              className="res-input res-mono"
              type="text"
              placeholder="Computed automatically when selecting a PDF"
              value={digest}
              aria-invalid={digestIssue ? true : undefined}
              aria-describedby={digestIssue ? "verify-digest-err" : undefined}
              onChange={e => {
                setDigest(e.target.value);
                if (status === "valid" || status === "invalid") setStatus("empty");
              }}
            />
            {digestIssue && (
              <span id="verify-digest-err" className="res-field-error" role="alert">
                {digestIssue.message}
              </span>
            )}
          </div>

          <button type="submit" className="primary" disabled={status === "pending"}>
            {status === "pending" ? "Verifying…" : "Verify report"}
          </button>
        </form>
      </section>
    </main>
  );
}
