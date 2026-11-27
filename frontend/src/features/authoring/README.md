# Authoring pages

| Route | Page | States covered |
| --- | --- | --- |
| `/examiner/exams` | `ExamRegister` | Loading, load error, empty register, empty filter, every exam state |
| `/examiner/exams/:id/edit` | `ExamEditor` | Editable draft, invalid total (mark ledger and checklist), unsaved changes, slot errors, publish confirmation, frozen paper, freshly copied draft |
| `/examiner/questions` | `QuestionBank` | Empty bank, no matches, detail with key, rubric, history and usage; revise; CSV import |
| `/examiner/exams/:id/enrollment` | `RosterPage` | Draft notice, empty roster, entry status per candidate, all-or-nothing enroll errors, CSV proofing report, closed roster |
| `/examiner/exams/:id/preview` | `PreviewPage` | Sandbox strip, empty paper, preview timer and five-minute warning, review, unrecorded receipt |

Each page takes `{ api, params, navigate }`. Mount them from `authoringRoutes` in `index.js`.

- **`HttpAuthoringApi`** (`mode: "live"`) calls the FastAPI router. The default prefix is `/api`, because `/me/exams` is both a page and an API path. Pass `csrfHeader` to match the platform's CSRF scheme.
- **`FixtureAuthoringApi`** (`mode: "preview"`) runs on fictional records in memory, with the same response and error shapes. Pages that run on it show a "Preview data" label.

To review without a backend, run `npm run dev` and open `/src/features/authoring/demo/index.html`.

## Design notes

The pages use the Folio tokens and classes (`folio.css`) and `PageHead` / `SaveStatus` from `Folio.jsx`. Feature styles live in `authoring.css` under an `au-` prefix:
- **Mark ledger:** one ruled bar with a segment for each slot, a dashed amber gap for unallocated marks and a rust limit line for overflow. A sentence below states the same facts in words.
- **Publication checklist:** the server's FR05 rules as ✓/✕ rows. Each failing slot links to its row.
- **Frozen seal:** a stamped record. Published particulars become a read-only list, not disabled inputs.
- **Proofing report:** import errors listed by row and field, beside the counts.
- **Window timeline:** the exam window as a ruler. The solid stretch is when a start still gets the full duration; the hatched stretch is when a start is cut short at closing (FR07's deadline rule). It shows the last full-length start time and updates live in the particulars form.
- **Paper profile:** the share of marks by difficulty, question type and topic, plus how many marks score automatically versus wait for an examiner. It follows unsaved slot edits.
- **Version comparison:** in the bank history, each revision opens a proof-reader's diff against the one before it: struck and inserted words in the prompt, changed particulars, and option or key moves matched by option ID.
- **Exam timetable:** the register shows the next fortnight as ruled day columns, with weekends shaded and a red "now" line. Each exam window is a bar in its state's style and links to the exam.
- **Galley proof:** a print-only A4 exam paper. "Print with key" adds the mark scheme and a Confidential watermark.
- **Ink details:** empty states use line drawings (register, card drawer, in-tray). The frozen seal is an SVG rubber stamp that stamps down on publish, honouring reduced motion. The bank record reads as a catalogue card.
- **Copy to new draft:** any exam, frozen or not, can seed a new draft with the same particulars and pinned versions. The roster is not copied.

State is always shown with text and a glyph as well as colour. Tables become labelled cards below 640 px, and dialogs trap focus and restore it on close.
