# Attempt API contract

This is the shared boundary between authoring, delivery and results. The SRS defines the remaining endpoints. A foundation PR records any contract change before dependent branches adopt it. Examples use symbolic IDs for readability. Entity IDs in the API are UUIDs.

| Operation | Contract |
| --- | --- |
| Publish | POST /exams/{exam_id}/publish freezes the question versions, marking rules and caps after validation. A 422 validation error identifies the item and field. The authoring owner supplies the immutable paper to delivery. |
| Enter | POST /exams/{exam_id}/attempts creates or resumes the eligible candidate's attempt. GET /attempts/{id} returns server_time, deadline_at, finalized_at, close_reason and items ordered by display_no. Each item exposes slot, kind, prompt, max_marks, ordered options (id and label), own accepted answer, flagged and revision. Grading keys and rubrics stay on the server. |
| Save | PUT /attempts/{id}/items/{slot} supplies base_revision, flagged and either selected_option_ids (integers scoped to the assigned version) or written_answer (string). An empty list or empty string clears a response. A 200 acknowledgment includes revision and saved_at. |
| Handle conflict | A 409 stale_revision includes the candidate's current item and revision. If normalized content already matches the accepted answer, return the canonical acknowledgment. A 409 attempt_closed includes the receipt. |
| Finalize | POST /attempts/{id}/submit returns attempt_id, finalized_at and close_reason (submitted or expired). A retry returns the same receipt. The deadline is absolute UTC and expiry wins at equality. Delivery owns the finalization transaction and calls the results-owned objective scoring policy within it. |
| Grade and release | PUT /attempts/{id}/items/{slot}/grade accepts awarded_marks in bounds on a finalized written item. Results owns the policy and grade endpoints. POST /exams/{id}/results/publish is owner-only and requires all real attempts finalized and fully graded after close. |
| Read results | GET /me/attempts/{id}/result returns an own released score and maximum. Unreleased or inaccessible private results return 404. Public report verification returns only a validity result. |

FastAPI owns eligibility, time and authorization. Use 401 for absent/expired sessions, 403 for disallowed roles, 404 for inaccessible private records, 409 for conflicts and 422 for invalid fields. Use ISO 8601 timestamps with an explicit offset. Review the implementation’s generated OpenAPI schema before merging integration.
