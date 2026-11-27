import React from "react";
import { attentionItems } from "../domain/insights.js";
import { paths } from "../paths.js";

const TONE = {
  urgent: { word: "Urgent", glyph: "!" },
  action: { word: "To do", glyph: "→" },
  info: { word: "Note", glyph: "i" },
};

/**
 * The examiner's in-tray: what needs them, most pressing first, each slip
 * with one action. Built from the register summary, so it needs no extra
 * requests. Tone is given in words and a glyph as well as colour.
 */
export function InTray({ exams, navigate, now = new Date(), limit = 6 }) {
  const notes = attentionItems(exams, now);
  const shown = notes.slice(0, limit);
  return <section className="au-intray" aria-labelledby="intray-title">
    <div className="au-intray__head">
      <h2 id="intray-title">In-tray</h2>
      <span className="au-sub">{notes.length ? `${notes.length} ${notes.length === 1 ? "slip needs" : "slips need"} you` : "Clear"}</span>
    </div>
    {notes.length === 0
      ? <p className="au-intray__clear"><b aria-hidden="true">✓</b> Nothing needs your attention. Unready drafts and empty rosters will land here.</p>
      : <ol className="au-intray__notes">{shown.map(n => <li key={n.key} className={`au-note au-note--${n.tone}`}>
          <span className="au-note__tab" aria-hidden="true">{TONE[n.tone].glyph}</span>
          <div className="au-note__text">
            <span className="au-note__tone">{TONE[n.tone].word}</span>
            <strong>{n.examTitle}</strong>
            <span className="au-note__title">{n.title}</span>
            <p>{n.detail}</p>
          </div>
          <button type="button" className="secondary au-note__go" onClick={() => navigate(paths[n.action.route](n.examId))}>
            {n.action.label}<span className="sr-only"> for {n.examTitle}</span></button>
        </li>)}</ol>}
    {notes.length > limit && <p className="au-sub au-intray__more">and {notes.length - limit} more below in the register.</p>}
  </section>;
}
