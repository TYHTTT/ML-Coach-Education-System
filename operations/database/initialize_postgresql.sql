-- Fresh installations only. Existing retired objects can be removed with
-- cleanup_retired.py --apply (automatic backup and transactional verification).
CREATE TABLE IF NOT EXISTS students (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE,
    display_name TEXT,
    password_hash TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL
);

ALTER TABLE students ADD COLUMN IF NOT EXISTS username TEXT UNIQUE;
ALTER TABLE students ADD COLUMN IF NOT EXISTS display_name TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1));

CREATE TABLE IF NOT EXISTS administrators (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    session_token_hash TEXT UNIQUE,
    session_expires_at TEXT,
    created_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL,
    CHECK ((session_token_hash IS NULL) = (session_expires_at IS NULL))
);

CREATE TABLE IF NOT EXISTS student_sessions (
    id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    description TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"'),
    updated_at TEXT NOT NULL DEFAULT to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"'),
    deleted_at TEXT
);

INSERT INTO courses(id, title, description, sort_order) VALUES
    ('machine_learning', '机器学习', '模型、算法与实践', 1),
    ('advanced_mathematics', '高等数学', '极限、微积分与定理', 2),
    ('linear_algebra', '线性代数', '向量、矩阵与几何', 3),
    ('probability_statistics', '概率论与统计基础', '概率、分布与统计', 4)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS curriculum_topics (
    id TEXT PRIMARY KEY,
    course TEXT NOT NULL REFERENCES courses(id),
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    stage INTEGER NOT NULL CHECK (stage > 0),
    stage_title TEXT NOT NULL,
    order_index INTEGER NOT NULL CHECK (order_index > 0),
    description TEXT NOT NULL,
    learning_objectives_json TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    retrieval_keywords_json TEXT NOT NULL,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')),
    required_dimensions_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(course, slug),
    CONSTRAINT curriculum_topics_id_course_key UNIQUE(id, course)
);

-- Undirected related-topic edges, independent of course directory placements.
CREATE TABLE IF NOT EXISTS topic_relations (
    topic_a_id TEXT NOT NULL REFERENCES curriculum_topics(id) ON DELETE CASCADE,
    topic_b_id TEXT NOT NULL REFERENCES curriculum_topics(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL DEFAULT 'related' CHECK (relation_type = 'related'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (topic_a_id, topic_b_id, relation_type),
    CHECK (topic_a_id < topic_b_id)
);
CREATE INDEX IF NOT EXISTS idx_topic_relations_b ON topic_relations(topic_b_id);

CREATE TABLE IF NOT EXISTS student_topic_states (
    student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL REFERENCES curriculum_topics(id) ON DELETE CASCADE,
    alpha REAL NOT NULL DEFAULT 1 CHECK (alpha > 0), beta REAL NOT NULL DEFAULT 1 CHECK (beta > 0),
    mastery REAL NOT NULL DEFAULT 0.5 CHECK (mastery BETWEEN 0 AND 1), confidence REAL NOT NULL DEFAULT 0 CHECK (confidence BETWEEN 0 AND 1),
    evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0), attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    practice_set_count INTEGER NOT NULL DEFAULT 0 CHECK (practice_set_count >= 0), checkpoint_count INTEGER NOT NULL DEFAULT 0 CHECK (checkpoint_count >= 0),
    latest_score REAL, best_score REAL, latest_checkpoint_score REAL,
    status TEXT NOT NULL DEFAULT 'not_started' CHECK (status IN ('not_started', 'learning', 'practicing', 'needs_remediation', 'ready_for_checkpoint', 'mastered')),
    started_at TEXT, last_practiced_at TEXT, mastered_at TEXT, updated_at TEXT NOT NULL,
    PRIMARY KEY (student_id, topic_id)
);

CREATE TABLE IF NOT EXISTS student_dimension_states (
    student_id TEXT NOT NULL, topic_id TEXT NOT NULL, dimension TEXT NOT NULL,
    alpha REAL NOT NULL DEFAULT 1 CHECK (alpha > 0), beta REAL NOT NULL DEFAULT 1 CHECK (beta > 0),
    mastery REAL NOT NULL DEFAULT 0.5 CHECK (mastery BETWEEN 0 AND 1), confidence REAL NOT NULL DEFAULT 0 CHECK (confidence BETWEEN 0 AND 1),
    evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0), updated_at TEXT NOT NULL,
    PRIMARY KEY (student_id, topic_id, dimension),
    FOREIGN KEY (student_id, topic_id) REFERENCES student_topic_states(student_id, topic_id) ON DELETE CASCADE
);

-- Read-only compatibility: existing course progress still reads historical results.
CREATE TABLE IF NOT EXISTS practice_sets (
    id TEXT PRIMARY KEY, student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL REFERENCES curriculum_topics(id) ON DELETE RESTRICT,
    course TEXT NOT NULL REFERENCES courses(id),
    mode TEXT NOT NULL CHECK (mode IN ('practice', 'checkpoint')),
    status TEXT NOT NULL CHECK (status IN ('generated', 'submitted', 'evaluation_uncertain')),
    requested_difficulty TEXT NOT NULL CHECK (requested_difficulty IN ('adaptive', 'easy', 'medium', 'hard')),
    source_snapshot_json TEXT NOT NULL, target_misconception_tags_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, submitted_at TEXT,
    purpose TEXT NOT NULL DEFAULT 'legacy',
    required_dimensions_snapshot_json TEXT
);

CREATE TABLE IF NOT EXISTS practice_questions (
    id TEXT PRIMARY KEY, practice_set_id TEXT NOT NULL REFERENCES practice_sets(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position > 0), question_type TEXT NOT NULL,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')), question TEXT NOT NULL, options_json TEXT,
    dimensions_json TEXT NOT NULL, answer_key_json TEXT NOT NULL, rubric_json TEXT NOT NULL, source_ids_json TEXT NOT NULL,
    question_hash TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE (practice_set_id, position),
    family_id TEXT,
    topic_ids_json TEXT NOT NULL DEFAULT '[]',
    competencies_json TEXT NOT NULL DEFAULT '[]',
    used_hint INTEGER NOT NULL DEFAULT 0,
    solution_revealed INTEGER NOT NULL DEFAULT 0,
    evidence_eligible INTEGER NOT NULL DEFAULT 1,
    attempt_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS practice_submissions (
    id TEXT PRIMARY KEY, practice_set_id TEXT NOT NULL REFERENCES practice_sets(id) ON DELETE CASCADE,
    student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE, client_submission_id TEXT NOT NULL UNIQUE,
    total_score REAL NOT NULL CHECK (total_score BETWEEN 0 AND 100),
    evaluation_status TEXT NOT NULL CHECK (evaluation_status IN ('processing', 'evaluated', 'evaluation_uncertain')),
    mastery_before REAL CHECK (mastery_before BETWEEN 0 AND 1), mastery_after REAL CHECK (mastery_after BETWEEN 0 AND 1),
    gate_result_json TEXT NOT NULL, response_json TEXT, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS practice_attempts (
    id TEXT PRIMARY KEY, submission_id TEXT NOT NULL REFERENCES practice_submissions(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL REFERENCES practice_questions(id) ON DELETE RESTRICT, student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    answer_text TEXT NOT NULL, score REAL NOT NULL CHECK (score BETWEEN 0 AND 100), verdict TEXT NOT NULL,
    dimension_scores_json TEXT NOT NULL, correct_points_json TEXT NOT NULL, missing_points_json TEXT NOT NULL, misconception_tags_json TEXT NOT NULL,
    critical_misconception INTEGER NOT NULL DEFAULT 0 CHECK (critical_misconception IN (0, 1)), feedback TEXT NOT NULL, reference_answer TEXT NOT NULL,
    evidence_source_ids_json TEXT NOT NULL, evaluator_confidence REAL NOT NULL CHECK (evaluator_confidence BETWEEN 0 AND 1),
    evaluation_reliable INTEGER NOT NULL CHECK (evaluation_reliable IN (0, 1)), created_at TEXT NOT NULL, UNIQUE (submission_id, question_id)
);

CREATE TABLE IF NOT EXISTS misconception_events (
    id TEXT PRIMARY KEY, student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL REFERENCES curriculum_topics(id) ON DELETE CASCADE, attempt_id TEXT NOT NULL REFERENCES practice_attempts(id) ON DELETE CASCADE,
    tag TEXT NOT NULL, critical INTEGER NOT NULL DEFAULT 0 CHECK (critical IN (0, 1)), evidence TEXT NOT NULL, created_at TEXT NOT NULL, resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS learning_sessions (
    id TEXT PRIMARY KEY, student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    course TEXT NOT NULL REFERENCES courses(id),
    topic_id TEXT REFERENCES curriculum_topics(id) ON DELETE SET NULL, state TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_placements (
    course_id TEXT NOT NULL REFERENCES courses(id), topic_id TEXT NOT NULL,
    parent_group_id TEXT NOT NULL, group_title TEXT NOT NULL, order_index INTEGER NOT NULL,
    PRIMARY KEY(course_id, topic_id),
    CONSTRAINT topic_placements_topic_course_fkey FOREIGN KEY(topic_id, course_id) REFERENCES curriculum_topics(id, course)
);

CREATE INDEX IF NOT EXISTS idx_curriculum_topics_course_stage_order ON curriculum_topics(course, active, stage, order_index);
CREATE INDEX IF NOT EXISTS idx_student_topic_states_topic_status ON student_topic_states(topic_id, status);
CREATE INDEX IF NOT EXISTS idx_student_topic_states_student_status ON student_topic_states(student_id, status);
CREATE INDEX IF NOT EXISTS idx_student_dimension_states_topic ON student_dimension_states(topic_id, dimension);
CREATE INDEX IF NOT EXISTS idx_practice_sets_student_topic_created ON practice_sets(student_id, topic_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_practice_sets_status ON practice_sets(status);
CREATE INDEX IF NOT EXISTS idx_practice_questions_hash ON practice_questions(question_hash);
CREATE INDEX IF NOT EXISTS idx_practice_submissions_student_created ON practice_submissions(student_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_practice_attempts_student_created ON practice_attempts(student_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_misconception_events_student_topic_unresolved ON misconception_events(student_id, topic_id, resolved_at);
CREATE INDEX IF NOT EXISTS idx_learning_sessions_student_course_updated ON learning_sessions(student_id, course, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_student_sessions_token_hash ON student_sessions(token_hash);

CREATE OR REPLACE FUNCTION enforce_registered_course() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM courses WHERE id = NEW.course AND deleted_at IS NULL) THEN
        RAISE EXCEPTION 'unregistered_course';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_curriculum_registered_course ON curriculum_topics;
CREATE TRIGGER trg_curriculum_registered_course BEFORE INSERT OR UPDATE ON curriculum_topics
FOR EACH ROW EXECUTE FUNCTION enforce_registered_course();
