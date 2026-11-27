"""Candidate delivery. Each public operation runs inside the caller's transaction.

Connections use psycopg's dict_row factory. score_objective is supplied by results.
"""
from datetime import timedelta, timezone
from random import SystemRandom
from uuid import uuid4

from fastapi import HTTPException

random = SystemRandom()


def fail(status, code, **fields):
    raise HTTPException(status, detail={"code": code, **fields})


def now(db):
    return db.execute("SELECT clock_timestamp() AS instant").fetchone()["instant"]


def candidate(db, account_id):
    account = db.execute("""
        SELECT enabled, font_percent, workspace_layout FROM account
        WHERE id = %s FOR SHARE
    """, (account_id,)).fetchone()
    if not account or not account["enabled"]:
        fail(401, "inactive_session")
    role = db.execute("""
        SELECT 1 FROM account_role WHERE account_id = %s
        AND role_name = 'candidate' FOR SHARE
    """, (account_id,)).fetchone()
    if not role:
        fail(403, "candidate_required")
    return account


def event(db, attempt_id, kind, instant):
    db.execute("""
        INSERT INTO attempt_event(id, attempt_id, kind, recorded_at)
        VALUES (%s,%s,%s,%s)
    """, (uuid4(), attempt_id, kind, instant))


def exams(db, account_id):
    candidate(db, account_id)
    instant = now(db)
    return db.execute("""
        SELECT e.id, e.title, e.instructions, e.opens_at, e.closes_at,
               e.duration_seconds, a.id AS attempt_id,
               CASE WHEN a.finalized_at IS NOT NULL OR %s >= e.closes_at
                         OR %s >= a.deadline_at THEN 'completed'
                    WHEN %s < e.opens_at THEN 'upcoming' ELSE 'available' END AS status
        FROM enrollment n JOIN exam e ON e.id = n.exam_id
        LEFT JOIN attempt a USING (exam_id, candidate_id)
        WHERE n.candidate_id = %s AND n.active AND e.published_at IS NOT NULL
        ORDER BY e.opens_at, e.title, e.id
    """, (instant, instant, instant, account_id)).fetchall()


def start(db, account_id, exam_id, score):
    candidate(db, account_id)
    exam = db.execute("""
        SELECT * FROM exam WHERE id=%s AND published_at IS NOT NULL FOR SHARE
    """, (exam_id,)).fetchone()
    enrolled = db.execute("""
        SELECT 1 FROM enrollment WHERE exam_id=%s AND candidate_id=%s AND active
        FOR UPDATE
    """, (exam_id, account_id)).fetchone()
    if not exam or not enrolled:
        fail(404, "unavailable")
    existing = db.execute("""
        SELECT id FROM attempt WHERE exam_id=%s AND candidate_id=%s
    """, (exam_id, account_id)).fetchone()
    if existing:
        return paper(db, account_id, existing["id"], score)
    instant = now(db)
    if not exam["opens_at"] <= instant < exam["closes_at"]:
        fail(409, "outside_exam_window")
    deadline = min(exam["closes_at"], instant + timedelta(seconds=exam["duration_seconds"]))
    attempt_id = uuid4()
    db.execute("""
        INSERT INTO attempt(id, exam_id, candidate_id, started_at, deadline_at)
        VALUES (%s,%s,%s,%s,%s)
    """, (attempt_id, exam_id, account_id, instant, deadline))
    items = db.execute("""
        SELECT i.slot, i.version_id, q.kind FROM exam_item i JOIN question_version q
        ON q.id=i.version_id WHERE exam_id=%s ORDER BY i.slot
    """, (exam_id,)).fetchall()
    if exam["shuffle_objective"]:
        positions = [i for i, item in enumerate(items) if item["kind"] != "written"]
        shuffled = random.sample([items[i] for i in positions], len(positions))
        for i, item in zip(positions, shuffled):
            items[i] = item
    for position, item in enumerate(items, 1):
        slot, version = item["slot"], item["version_id"]
        db.execute("""
            INSERT INTO attempt_item(attempt_id,exam_id,slot,version_id,display_no)
            VALUES (%s,%s,%s,%s,%s)
        """, (attempt_id, exam_id, slot, version, position))
        db.execute("""
            INSERT INTO attempt_option(attempt_id,slot,version_id,option_no,display_no)
            SELECT %s,%s,version_id,option_no,row_number() OVER
            (ORDER BY CASE WHEN %s THEN random() END, option_no)
            FROM question_option WHERE version_id=%s
        """, (attempt_id, slot, exam["shuffle_choices"], version))
    event(db, attempt_id, "started", instant)
    return paper(db, account_id, attempt_id, score)


def lock_owned(db, account_id, attempt_id):
    account = candidate(db, account_id)
    eligible = db.execute("""
        SELECT 1 FROM attempt a JOIN enrollment n USING (exam_id,candidate_id)
        WHERE a.id=%s AND a.candidate_id=%s AND n.active FOR SHARE OF n
    """, (attempt_id, account_id)).fetchone()
    if not eligible:
        fail(404, "unavailable")
    attempt = db.execute("""
        SELECT a.*, e.title FROM attempt a JOIN exam e ON e.id=a.exam_id
        WHERE a.id=%s AND a.candidate_id=%s FOR UPDATE OF a
    """, (attempt_id, account_id)).fetchone()
    if not attempt:
        fail(404, "unavailable")
    return attempt, account, now(db)


def finish(db, attempt, instant, score, submit=False):
    if not attempt["finalized_at"]:
        expired = instant >= attempt["deadline_at"]
        if not expired and not submit:
            return None
        rows = db.execute("""
            SELECT i.slot,i.written_answer,q.kind,q.marking_rule,e.max_marks,
                   ARRAY(SELECT option_no FROM attempt_option o WHERE o.attempt_id=i.attempt_id
                         AND o.slot=i.slot AND o.selected) AS selections,
                   ARRAY(SELECT option_no FROM question_option o WHERE o.version_id=i.version_id
                         AND o.is_correct) AS correct
            FROM attempt_item i JOIN exam_item e USING (exam_id,slot,version_id)
            JOIN question_version q ON q.id=i.version_id WHERE i.attempt_id=%s
        """, (attempt["id"],)).fetchall()
        for row in rows:
            if row["kind"] == "written":
                award = None if row["written_answer"].strip() else 0
            else:
                award = score(row["kind"], set(row["selections"]), set(row["correct"]),
                              row["marking_rule"], row["max_marks"])
            db.execute("UPDATE attempt_item SET awarded_marks=%s WHERE attempt_id=%s AND slot=%s",
                       (award, attempt["id"], row["slot"]))
        attempt["close_reason"] = "expired" if expired else "submitted"
        attempt["finalized_at"] = instant
        db.execute("UPDATE attempt SET finalized_at=%s, close_reason=%s WHERE id=%s",
                   (instant, attempt["close_reason"], attempt["id"]))
        event(db, attempt["id"], attempt["close_reason"], instant)
    return {"attempt_id": attempt["id"], "finalized_at": attempt["finalized_at"].astimezone(timezone.utc).isoformat(),
            "close_reason": attempt["close_reason"]}


def read_items(db, attempt_id, slot=None):
    return db.execute("""
        SELECT i.slot,i.display_no,q.prompt,q.kind,e.max_marks,i.written_answer,
               i.flagged,i.answer_revision AS revision,i.saved_at,
               ARRAY(SELECT option_no FROM attempt_option o WHERE o.attempt_id=i.attempt_id
                     AND o.slot=i.slot AND o.selected ORDER BY option_no) AS selected_option_ids,
               COALESCE((SELECT jsonb_agg(jsonb_build_object('id',o.option_no,'label',b.label)
                             ORDER BY o.display_no) FROM attempt_option o JOIN question_option b
                             USING (version_id,option_no) WHERE o.attempt_id=i.attempt_id
                             AND o.slot=i.slot),'[]'::jsonb) AS options
        FROM attempt_item i JOIN exam_item e USING (exam_id,slot,version_id)
        JOIN question_version q ON q.id=i.version_id
        WHERE i.attempt_id=%s AND (%s::integer IS NULL OR i.slot=%s) ORDER BY i.display_no
    """, (attempt_id, slot, slot)).fetchall()


def paper(db, account_id, attempt_id, score):
    attempt, account, instant = lock_owned(db, account_id, attempt_id)
    receipt = finish(db, attempt, instant, score)
    return {"attempt_id": attempt_id, "exam_id": attempt["exam_id"], "title": attempt["title"],
            "server_time": instant, "deadline_at": attempt["deadline_at"],
            "finalized_at": receipt["finalized_at"] if receipt else None, "close_reason": attempt["close_reason"],
            "preferences": {k: account[k] for k in ("font_percent", "workspace_layout")},
            "items": read_items(db, attempt_id)}


def save(db, account_id, attempt_id, slot, edit, score):
    attempt, _, instant = lock_owned(db, account_id, attempt_id)
    receipt = finish(db, attempt, instant, score)
    if receipt:
        # Return a conflict value so expiry commits before the HTTP 409.
        return 409, {"code": "attempt_closed", "receipt": receipt}
    rows = read_items(db, attempt_id, slot)
    if not rows:
        fail(404, "unavailable")
    item = rows[0]
    written = item["kind"] == "written"
    ids = edit.selected_option_ids
    if written != (edit.written_answer is not None) or written == (ids is not None):
        fail(422, "invalid_answer_type")
    if ids is not None and (len(ids) != len(set(ids)) or
                            not set(ids) <= {o["id"] for o in item["options"]} or
                            (item["kind"] == "single" and len(ids) > 1)):
        fail(422, "invalid_options")
    if edit.base_revision != item["revision"]:
        matches = (edit.written_answer == item["written_answer"] if written else
                   sorted(ids) == item["selected_option_ids"])
        if edit.base_revision < item["revision"] and matches and edit.flagged == item["flagged"]:
            return 200, {"revision": item["revision"], "saved_at": item["saved_at"]}
        return 409, {"code": "stale_revision", "item": item}
    if not written:
        db.execute("UPDATE attempt_option SET selected=(option_no=ANY(%s::integer[])) "
                   "WHERE attempt_id=%s AND slot=%s", (ids, attempt_id, slot))
    ack = db.execute("""
        UPDATE attempt_item SET flagged=%s,written_answer=%s,answer_revision=answer_revision+1,
        saved_at=%s WHERE attempt_id=%s AND slot=%s RETURNING answer_revision AS revision,saved_at
    """, (edit.flagged, edit.written_answer or "", instant, attempt_id, slot)).fetchone()
    return 200, ack


def expire_due(connect, score_objective, limit=64):
    """Run from the platform scheduler, including at startup. One transaction per attempt."""
    for count in range(limit):
        with connect() as db:
            attempt = db.execute("""
                SELECT * FROM attempt WHERE finalized_at IS NULL AND deadline_at<=clock_timestamp()
                ORDER BY deadline_at LIMIT 1 FOR UPDATE SKIP LOCKED
            """).fetchone()
            if not attempt:
                return count
            finish(db, attempt, now(db), score_objective)
    return limit
