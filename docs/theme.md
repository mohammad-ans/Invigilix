# Folio design language

Folio borrows from an examiner’s paper register. The paper is warm, the masthead is forest green, and numbered entries do the work of decoration. A field-survey plate appears because the question asks the candidate to interpret it.

| Token | Value | Use |
| --- | --- | --- |
| Paper / sheet | #F6F4EC / #FFFEF9 | Page and reading surface |
| Graphite / forest | #202F2A / #183F36 | Body text, masthead, current question and primary action |
| Sage | #E5EDDF | Selected answer with a radio, checkbox or checkmark |
| Amber / pale amber | #765415 / #F7EDD2 | Pending local work and review flags with a text label |
| Rust / pale rust | #953E2C / #F8E2D9 | Failed saves or expired time with an explicit message |
| Focus | #165E96 | Keyboard focus outline |

Use the reading serif for exam titles and questions, the sans serif for actions and body copy, and monospace for question IDs, scores, timestamps and the countdown. CSS specifies local fallbacks so the theme works offline. Keep corners at 4 px, borders one pixel, layouts on an 8 px rhythm, and surfaces flat. The asset and shared CSS are in frontend/public and frontend/src/design.

On desktop an attempt has a wide reading column and a narrower answer sheet. Below 820 px the columns stack. At 360 px all essential controls remain reachable. The answer sheet uses text, checkmarks and flag shapes alongside color. Use focus-visible outlines and announce consequential save failures. Give examiners dense readable tables and candidates generous reading space. Monitor labels describe observable events.

Before accepting a page, inspect the desktop layout, the 360 px layout, keyboard focus, the 200% reading-size setting, and one error state. Freeze accepted references on main. Change shared tokens or reference screens through a foundation PR.
