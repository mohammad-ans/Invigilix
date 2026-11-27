import React from "react";
import { versionChanges } from "../domain/diff.js";
import { KIND, RULE } from "../domain/format.js";

const show = (key, value) => (!value ? "none" : key === "kind" ? KIND[value]?.label ?? value : key === "marking_rule" ? RULE[value] ?? value : value);

/** A proof-reader's view of one revision: struck-out and inserted words,
 *  changed particulars, and option or key moves matched by option ID. */
export function VersionDiff({ prev, next }) {
  const c = versionChanges(prev, next);
  if (c.empty) return <p className="au-sub">No content changes.</p>;
  return <div className="au-diff">
    {c.prompt && <p className="au-diff__prompt">{c.prompt.map((part, n) => part.op === "same" ? <span key={n}>{part.text}</span>
      : part.op === "del" ? <del key={n}><span className="sr-only">removed: </span>{part.text}</del>
        : <ins key={n}><span className="sr-only">added: </span>{part.text}</ins>)}</p>}
    {c.fields.length > 0 && <ul className="au-diff__list">{c.fields.map(f => <li key={f.key}>
      <span className="au-diff__what">{f.label}</span> <del>{show(f.key, f.from)}</del> <span aria-hidden="true">→</span><span className="sr-only">changed to</span> <ins>{show(f.key, f.to)}</ins></li>)}</ul>}
    {c.options.length > 0 && <ul className="au-diff__list">{c.options.map(o => <li key={o.id + o.change}>
      <span className="au-diff__what">Option {o.id}</span>{" "}
      {o.change === "added" && <ins>{o.label}{o.correct ? " (key)" : ""}</ins>}
      {o.change === "removed" && <del>{o.label}{o.correct ? " (key)" : ""}</del>}
      {o.change === "changed" && <>
        {o.relabeled && <><del>{o.from}</del> <span aria-hidden="true">→</span><span className="sr-only">relabelled</span> <ins>{o.label}</ins> </>}
        {o.keyNow === true && <span className="au-diff__key au-diff__key--on">✓ now the key</span>}
        {o.keyNow === false && <span className="au-diff__key">no longer a key</span>}
        {!o.relabeled && o.keyNow !== undefined && <span className="au-sub au-inline"> · {o.label}</span>}
      </>}
    </li>)}</ul>}
  </div>;
}
