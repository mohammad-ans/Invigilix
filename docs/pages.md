# Page assignments and design contracts

Use the route and screen hierarchy below as the baseline. Each feature exports its pages from its own directory. The platform maintainer mounts them in the router. Every page uses the Folio masthead, shared type and spacing, visible keyboard focus, and access-appropriate response data. The role selector belongs to the theme preview. The production shell derives routes and actions from the authenticated account.

| Owner | Route and screen | Page hierarchy and required states |
| --- | --- | --- |
| Foundation | /login, /admin/accounts | Labeled sign-in form. Account register with role and access columns, search, admin-only actions, empty state and validation feedback. Use the administrator preview. |
| Authoring | /examiner/exams, /examiner/exams/:id/edit | Exam register then editor. Title, timing, duration, declared total, item slots, preview, publish. Distinguish editable draft, invalid total, and frozen published paper. |
| Authoring | /examiner/questions, /examiner/exams/:id/enrollment | Filterable bank with version, type, topic and difficulty. Scoped roster plus CSV validation summary with row and field errors. Admin import action uses the foundation identity service. |
| Authoring | /examiner/exams/:id/preview | Render the candidate page with a transient preview adapter and a visible preview label. No real attempt or statistics. Draft-paper fixture unblocks development until delivery exports its page. |
| Delivery | /me/exams | Candidate exam list organized by upcoming, available and completed. Each entry has instructions, schedule and one permitted next action. Include an empty assignment state. |
| Delivery | /attempts/:id | Use the candidate reference. Heading and timer, ordered question panel, save status, answer sheet, review, scratchpad and preferences. Support single, multiple and written responses, offline queue, conflict, expiry and final receipt. |
| Results | /examiner/exams/:id/monitor | Use the examiner reference. Roster with counts and progress, incident timeline, announcement input. Reconnect is a neutral observation. Add empty and stale-feed states. |
| Results | /examiner/exams/:id/marking, /examiner/exams/:id/results | Written response with cap, numeric award and validation. Grade status and release gate alongside class summary, question statistics and authorized PDF export. Include pending and zero-exposure states. |
| Results | /me/attempts/:id/result, /verify | Own released score and issued PDF. Public verification accepts code and digest and returns validity only. Keep denied, pending, invalid-file and empty states distinct. |

Production labels for persistence are “Saving”, “On this device”, “Saved on server” and “Save failed”. An acknowledgment from FastAPI is required for “Saved on server”. The preview uses fictional records and session-local state so its label is “Saved in this preview”.
