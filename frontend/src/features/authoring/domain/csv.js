// Minimal RFC 4180 reader used for file previews and by the fixture adapter.
// Rows carry their 1-based line number so errors match the server's "row".

export function parseCsv(text) {
  const records = [];
  let row = [], field = "", quoted = false, line = 1, rowLine = 1;
  const source = text.replace(/^﻿/, "");
  const endField = () => { row.push(field); field = ""; };
  const endRow = () => {
    endField();
    if (row.some(v => v.trim() !== "")) records.push({ line: rowLine, values: row });
    row = [];
  };
  for (let i = 0; i < source.length; i++) {
    const ch = source[i];
    if (quoted) {
      if (ch === '"' && source[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') quoted = false;
      else { if (ch === "\n") line++; field += ch; }
    } else if (ch === '"') quoted = true;
    else if (ch === ",") endField();
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && source[i + 1] === "\n") i++;
      endRow(); line++; rowLine = line;
    } else field += ch;
  }
  if (field !== "" || row.length) endRow();
  if (quoted) throw new Error("A quoted value is not closed.");
  const [head, ...body] = records;
  const header = (head?.values ?? []).map(h => h.trim());
  return {
    header,
    rows: body.map(r => ({
      row: r.line,
      extra: r.values.length > header.length,
      values: Object.fromEntries(header.map((h, i) => [h, (r.values[i] ?? "").trim()])),
    })),
  };
}

export const TEMPLATES = {
  questions: {
    filename: "question-bank-template.csv",
    text: 'question_id,topic,difficulty,kind,prompt,marking_rule,options,correct_option_ids,rubric\n' +
      '8f1c2a4e-0d5b-4e7a-9c11-2b6f9a1d3e70,Ecology,easy,single,Which factor is abiotic?,exact,"[{""id"":1,""label"":""Light intensity""},{""id"":2,""label"":""Rabbit population""}]","[1]",\n',
  },
  roster: { filename: "roster-template.csv", text: "candidate_email\nnora.khan@example.test\n" },
  candidates: { filename: "candidates-template.csv", text: "email,display_name\nnora.khan@example.test,Nora Khan\n" },
};
