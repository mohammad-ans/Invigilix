import React from "react";

// Ink line drawings for empty states. One pen weight, graphite strokes, a
// single rust accent (the margin rule an examiner draws in red). They scale
// with currentColor and carry no meaning on their own: every empty state also
// says in words what is missing.

const ink = { fill: "none", stroke: "currentColor", strokeWidth: 1.3, strokeLinecap: "round", strokeLinejoin: "round" };

/** An open register: ruled pages, red margin, a pen resting across it. */
export function LedgerArt() {
  const rules = [34, 42, 50, 58, 66, 74];
  return <svg className="au-art" viewBox="0 0 168 104" width="168" height="104" aria-hidden="true" {...ink}>
    <path d="M84 24c-17-6-40-7-66-3v64c26-4 49-3 66 3z" fill="var(--sheet)" />
    <path d="M84 24c17-6 40-7 66-3v64c-26-4-49-3-66 3z" fill="var(--sheet)" />
    <path d="M84 24v64" />
    {rules.map(y => <path key={"l" + y} d={`M24 ${y - 1}c18-2.6 38-2.4 54 1.2`} strokeWidth=".7" opacity=".55" />)}
    {rules.map(y => <path key={"r" + y} d={`M90 ${y + .2}c16-3.6 36-3.8 54-1.2`} strokeWidth=".7" opacity=".55" />)}
    <path d="M34 27.5v56" stroke="var(--rust)" strokeWidth=".9" />
    <path d="M27 33.5h4M27 41.5h4" strokeWidth=".9" />
    <path d="M112 74l42-36 4 3.5-42 36-6 2.6z" fill="var(--sheet)" />
    <path d="M110 80l2-5.5 4 3.4" />
    <path d="M146 45l4 3.4" />
  </svg>;
}

/** A catalogue drawer: three index cards standing in a box, one tabbed. */
export function CardDrawerArt() {
  return <svg className="au-art" viewBox="0 0 168 104" width="168" height="104" aria-hidden="true" {...ink}>
    <path d="M46 40h76l-3 10H49z" fill="var(--sheet)" />
    <path d="M52 20h56v26H52z" fill="var(--sheet)" transform="rotate(-6 80 33)" />
    <path d="M56 16h56v30H56z" fill="var(--sheet)" />
    <path d="M60 12h48v6H60z" fill="var(--sheet)" transform="rotate(4 84 15)" />
    <path d="M90 8.5h14v6H90" stroke="var(--rust)" />
    <path d="M62 24h30M62 30h40M62 36h24" strokeWidth=".7" opacity=".6" />
    <path d="M40 46h88v42H40z" fill="var(--sheet)" />
    <path d="M70 60h28v10H70z" />
    <path d="M78 65h12" strokeWidth=".8" />
    <circle cx="84" cy="78" r="2.4" />
    <path d="M40 88l-4 4h96l-4-4" />
  </svg>;
}

/** An in-tray holding a stack of loose sheets, the top one ruled like a CSV. */
export function TrayArt() {
  return <svg className="au-art" viewBox="0 0 168 104" width="168" height="104" aria-hidden="true" {...ink}>
    <path d="M52 20h62v48H52z" fill="var(--sheet)" transform="rotate(-5 83 44)" />
    <path d="M56 16h62v50H56z" fill="var(--sheet)" transform="rotate(3 87 41)" />
    <path d="M60 22h44M60 30h44M60 38h44M60 46h44" strokeWidth=".7" opacity=".6" transform="rotate(3 87 41)" />
    <path d="M74 20v32M90 20v32" strokeWidth=".7" opacity=".6" transform="rotate(3 87 41)" />
    <path d="M28 58h112l-10 26H38z" fill="var(--sheet)" />
    <path d="M28 58l6-6h100l6 6" />
    <path d="M66 70h36" stroke="var(--rust)" />
  </svg>;
}
