-- Secure Examination Management System | Proposed PostgreSQL schema
-- Apply once to an empty database. FastAPI supplies UUIDs, UTC instants and
-- cryptographically random report codes. Use parameterized SQL or SQLAlchemy.
-- Mutations run through the transaction rules in the accompanying design.
BEGIN;

CREATE TABLE account (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL CHECK (length(trim(email)) > 0),
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
    password_hash TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    font_percent SMALLINT NOT NULL DEFAULT 100 CHECK (font_percent BETWEEN 80 AND 200),
    workspace_layout TEXT NOT NULL DEFAULT 'standard'
        CHECK (workspace_layout IN ('standard', 'focus'))
);
CREATE UNIQUE INDEX account_email_ci ON account (lower(trim(email)));

CREATE TABLE account_role (
    account_id UUID NOT NULL REFERENCES account (id),
    role_name TEXT NOT NULL CHECK (role_name IN ('admin', 'examiner', 'candidate')),
    PRIMARY KEY (account_id, role_name)
);

CREATE TABLE login_session (
    token_hash TEXT PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES account (id),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX login_session_account ON login_session (account_id);

-- A bank edit locks the question, then inserts a whole new version and option set.
-- Existing versions are immutable. Keys are private examiner/grading data.
CREATE TABLE question (
    id UUID PRIMARY KEY,
    owner_id UUID NOT NULL REFERENCES account (id)
);
CREATE INDEX question_owner ON question (owner_id);

CREATE TABLE question_version (
    id UUID PRIMARY KEY,
    question_id UUID NOT NULL REFERENCES question (id),
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    topic TEXT NOT NULL CHECK (length(trim(topic)) > 0),
    difficulty TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')),
    prompt TEXT NOT NULL CHECK (length(trim(prompt)) > 0),
    kind TEXT NOT NULL CHECK (kind IN ('single', 'multiple', 'written')),
    marking_rule TEXT NOT NULL,
    rubric TEXT,
    UNIQUE (question_id, version_no),
    CHECK ((kind = 'single' AND marking_rule = 'exact') OR
           (kind = 'multiple' AND marking_rule IN ('exact', 'partial_no_wrong')) OR
           (kind = 'written' AND marking_rule = 'manual'))
);

CREATE TABLE question_option (
    version_id UUID NOT NULL REFERENCES question_version (id),
    option_no SMALLINT NOT NULL CHECK (option_no > 0),
    label TEXT NOT NULL CHECK (length(trim(label)) > 0),
    is_correct BOOLEAN NOT NULL,
    PRIMARY KEY (version_id, option_no)
);

-- Effective exam state is derived from publication, the window and DB time.
CREATE TABLE exam (
    id UUID PRIMARY KEY,
    owner_id UUID NOT NULL REFERENCES account (id),
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    instructions TEXT NOT NULL,
    opens_at TIMESTAMPTZ NOT NULL,
    closes_at TIMESTAMPTZ NOT NULL,
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds > 0),
    total_marks NUMERIC(8,2) NOT NULL CHECK (total_marks > 0),
    shuffle_objective BOOLEAN NOT NULL DEFAULT FALSE,
    shuffle_choices BOOLEAN NOT NULL DEFAULT FALSE,
    published_at TIMESTAMPTZ,
    results_published_at TIMESTAMPTZ,
    CHECK (closes_at > opens_at),
    CHECK (published_at IS NULL OR published_at < closes_at),
    CHECK (results_published_at IS NULL OR
           (published_at IS NOT NULL AND results_published_at >= closes_at))
);
CREATE INDEX exam_owner ON exam (owner_id);

CREATE TABLE exam_item (
    exam_id UUID NOT NULL REFERENCES exam (id),
    slot SMALLINT NOT NULL CHECK (slot > 0),
    version_id UUID NOT NULL REFERENCES question_version (id),
    max_marks NUMERIC(8,2) NOT NULL CHECK (max_marks > 0),
    PRIMARY KEY (exam_id, slot),
    UNIQUE (exam_id, version_id),
    UNIQUE (exam_id, slot, version_id)
);

CREATE TABLE enrollment (
    exam_id UUID NOT NULL REFERENCES exam (id),
    candidate_id UUID NOT NULL REFERENCES account (id),
    enrolled_by UUID NOT NULL REFERENCES account (id),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (exam_id, candidate_id)
);
CREATE INDEX enrollment_candidate ON enrollment (candidate_id, exam_id);

-- Real attempts only. A sandbox is a transient examiner-owned preview.
CREATE TABLE attempt (
    id UUID PRIMARY KEY,
    exam_id UUID NOT NULL,
    candidate_id UUID NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    deadline_at TIMESTAMPTZ NOT NULL,
    finalized_at TIMESTAMPTZ,
    close_reason TEXT,
    FOREIGN KEY (exam_id, candidate_id) REFERENCES enrollment (exam_id, candidate_id),
    UNIQUE (exam_id, candidate_id),
    UNIQUE (id, exam_id),
    CHECK (deadline_at > started_at),
    CHECK ((finalized_at IS NULL AND close_reason IS NULL) OR
           (finalized_at IS NOT NULL AND close_reason IS NOT NULL AND
            ((close_reason = 'submitted' AND finalized_at >= started_at AND finalized_at < deadline_at) OR
             (close_reason = 'expired' AND finalized_at >= deadline_at))))
);
CREATE INDEX attempt_expiry ON attempt (deadline_at) WHERE finalized_at IS NULL;

-- slot identifies an exam item; display_no records the candidate's permutation.
-- The two composite foreign keys prevent assigning an item from another exam.
CREATE TABLE attempt_item (
    attempt_id UUID NOT NULL,
    exam_id UUID NOT NULL,
    slot SMALLINT NOT NULL,
    version_id UUID NOT NULL,
    display_no SMALLINT NOT NULL CHECK (display_no > 0),
    written_answer TEXT NOT NULL DEFAULT '',
    flagged BOOLEAN NOT NULL DEFAULT FALSE,
    answer_revision INTEGER NOT NULL DEFAULT 0 CHECK (answer_revision >= 0),
    saved_at TIMESTAMPTZ,
    awarded_marks NUMERIC(8,2) CHECK (awarded_marks >= 0),
    graded_by UUID REFERENCES account (id),
    PRIMARY KEY (attempt_id, slot),
    UNIQUE (attempt_id, display_no),
    UNIQUE (attempt_id, slot, version_id),
    FOREIGN KEY (attempt_id, exam_id) REFERENCES attempt (id, exam_id),
    FOREIGN KEY (exam_id, slot, version_id) REFERENCES exam_item (exam_id, slot, version_id)
);

-- The candidate can select only choices materialized for this assigned item.
CREATE TABLE attempt_option (
    attempt_id UUID NOT NULL,
    slot SMALLINT NOT NULL,
    version_id UUID NOT NULL,
    option_no SMALLINT NOT NULL,
    display_no SMALLINT NOT NULL CHECK (display_no > 0),
    selected BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (attempt_id, slot, option_no),
    UNIQUE (attempt_id, slot, display_no),
    FOREIGN KEY (attempt_id, slot, version_id) REFERENCES attempt_item (attempt_id, slot, version_id),
    FOREIGN KEY (version_id, option_no) REFERENCES question_option (version_id, option_no)
);

CREATE TABLE attempt_event (
    id UUID PRIMARY KEY,
    attempt_id UUID NOT NULL REFERENCES attempt (id),
    kind TEXT NOT NULL CHECK (kind IN ('started', 'reconnected', 'reported_incident', 'submitted', 'expired')),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note TEXT
);
CREATE INDEX attempt_event_timeline ON attempt_event (attempt_id, recorded_at);

CREATE TABLE announcement (
    id UUID PRIMARY KEY,
    exam_id UUID NOT NULL REFERENCES exam (id),
    author_id UUID NOT NULL REFERENCES account (id),
    posted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    message TEXT NOT NULL CHECK (length(trim(message)) > 0)
);
CREATE INDEX announcement_timeline ON announcement (exam_id, posted_at);

-- Issue after result release. The digest covers the final, exact PDF bytes.
-- The public verifier accepts the code and digest and returns a validity bit.
CREATE TABLE result_report (
    verification_code TEXT PRIMARY KEY,
    attempt_id UUID NOT NULL UNIQUE REFERENCES attempt (id),
    issued_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sha256_hex TEXT NOT NULL CHECK (length(sha256_hex) = 64),
    pdf_bytes BYTEA NOT NULL
);

-- Compute totals from a single authoritative set of awards. An incomplete
-- written grade leaves total_score NULL instead of silently counting as zero.
CREATE VIEW attempt_score AS
SELECT a.id AS attempt_id, a.exam_id, a.candidate_id,
       COUNT(i.slot) AS item_count,
       COUNT(i.awarded_marks) AS graded_count,
       CASE WHEN COUNT(i.slot) > 0 AND COUNT(i.awarded_marks) = COUNT(i.slot)
            THEN SUM(i.awarded_marks) END AS total_score
FROM attempt AS a
JOIN attempt_item AS i ON i.attempt_id = a.id
WHERE a.finalized_at IS NOT NULL
GROUP BY a.id, a.exam_id, a.candidate_id;

-- FastAPI transaction invariants (cross-row and time-dependent):
-- Publish locks the exam, validates question ownership, one bank identity per
-- exam, option/key cardinality and SUM(max_marks) = total_marks, then freezes it.
-- Start takes FOR SHARE on exam then FOR UPDATE on enrollment, checks the
-- published window, role and eligibility. Atomically create one attempt with
-- its complete paper and absolute deadline, or return the prior attempt.
-- Save/close lock the attempt first. Check clock_timestamp() after lock
-- acquisition. Save enforces response shape, option membership and base revision.
-- Finalization writes objective/blank awards, time, reason and event atomically.
-- Manual grade and release take FOR UPDATE on the exam first. Cap awards by
-- exam_item.max_marks. Release only after close, with no active attempts or
-- pending marks. Freeze released awards.
-- Account disable/role changes and resource ownership are checked on protected
-- operations. Deactivate identities/enrollments rather than deleting history.
COMMIT;
