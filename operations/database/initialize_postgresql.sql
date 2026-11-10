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
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

INSERT INTO courses(id, title) VALUES
    ('machine_learning', '机器学习'),
    ('advanced_mathematics', '高等数学'),
    ('linear_algebra', '线性代数'),
    ('probability_statistics', '概率论与统计基础')
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS curriculum_topics (
    id TEXT PRIMARY KEY,
    course TEXT NOT NULL CHECK (course IN ('machine_learning', 'advanced_mathematics', 'linear_algebra', 'probability_statistics')),
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
    UNIQUE(course, slug)
);

CREATE TABLE IF NOT EXISTS topic_prerequisites (
    topic_id TEXT NOT NULL REFERENCES curriculum_topics(id) ON DELETE CASCADE,
    prerequisite_topic_id TEXT NOT NULL REFERENCES curriculum_topics(id) ON DELETE RESTRICT,
    required_mastery REAL NOT NULL DEFAULT 0.8 CHECK (required_mastery BETWEEN 0 AND 1),
    relation_type TEXT NOT NULL DEFAULT 'required' CHECK (relation_type IN ('required', 'recommended', 'related')),
    reason TEXT NOT NULL DEFAULT '掌握这一基础有助于完成当前知识点的正式验收。',
    required_competencies_json TEXT NOT NULL DEFAULT '[]',
    scope TEXT NOT NULL DEFAULT 'topic' CHECK (scope IN ('topic', 'lesson_section')),
    section_id TEXT NOT NULL DEFAULT '',
    rule_version TEXT NOT NULL DEFAULT 'content-v1',
    PRIMARY KEY(topic_id, prerequisite_topic_id, relation_type, scope, section_id),
    CHECK(topic_id <> prerequisite_topic_id)
);

CREATE TABLE IF NOT EXISTS student_topic_states (
    student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL REFERENCES curriculum_topics(id) ON DELETE CASCADE,
    alpha REAL NOT NULL DEFAULT 1 CHECK (alpha > 0), beta REAL NOT NULL DEFAULT 1 CHECK (beta > 0),
    mastery REAL NOT NULL DEFAULT 0.5 CHECK (mastery BETWEEN 0 AND 1), confidence REAL NOT NULL DEFAULT 0 CHECK (confidence BETWEEN 0 AND 1),
    evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0), attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    practice_set_count INTEGER NOT NULL DEFAULT 0 CHECK (practice_set_count >= 0), checkpoint_count INTEGER NOT NULL DEFAULT 0 CHECK (checkpoint_count >= 0),
    latest_score REAL, best_score REAL, latest_checkpoint_score REAL,
    status TEXT NOT NULL DEFAULT 'not_started' CHECK (status IN ('locked', 'not_started', 'learning', 'practicing', 'needs_remediation', 'ready_for_checkpoint', 'mastered')),
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

CREATE TABLE IF NOT EXISTS practice_sets (
    id TEXT PRIMARY KEY, student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL REFERENCES curriculum_topics(id) ON DELETE RESTRICT,
    course TEXT NOT NULL CHECK (course IN ('machine_learning', 'advanced_mathematics', 'linear_algebra', 'probability_statistics')),
    mode TEXT NOT NULL CHECK (mode IN ('practice', 'checkpoint')),
    status TEXT NOT NULL CHECK (status IN ('generated', 'submitted', 'evaluation_uncertain')),
    requested_difficulty TEXT NOT NULL CHECK (requested_difficulty IN ('adaptive', 'easy', 'medium', 'hard')),
    source_snapshot_json TEXT NOT NULL, target_misconception_tags_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, submitted_at TEXT,
    purpose TEXT NOT NULL DEFAULT 'legacy',
    prerequisite_for TEXT REFERENCES curriculum_topics(id),
    rule_version TEXT NOT NULL DEFAULT 'legacy',
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
    course TEXT NOT NULL CHECK (course IN ('machine_learning', 'advanced_mathematics', 'linear_algebra', 'probability_statistics')),
    topic_id TEXT REFERENCES curriculum_topics(id) ON DELETE SET NULL, state TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_placements (
    course_id TEXT NOT NULL REFERENCES courses(id), topic_id TEXT NOT NULL REFERENCES curriculum_topics(id),
    parent_group_id TEXT NOT NULL, group_title TEXT NOT NULL, order_index INTEGER NOT NULL,
    is_reference INTEGER NOT NULL DEFAULT 0 CHECK (is_reference IN (0, 1)), PRIMARY KEY(course_id, topic_id)
);

CREATE TABLE IF NOT EXISTS prerequisite_verifications (
    student_id TEXT NOT NULL REFERENCES students(id), dependent_topic_id TEXT NOT NULL REFERENCES curriculum_topics(id),
    prerequisite_topic_id TEXT NOT NULL REFERENCES curriculum_topics(id), competency TEXT NOT NULL,
    rule_version TEXT NOT NULL, assessment_id TEXT NOT NULL REFERENCES practice_sets(id), verified_at TEXT NOT NULL,
    PRIMARY KEY(student_id, dependent_topic_id, prerequisite_topic_id, competency, rule_version)
);

CREATE TABLE IF NOT EXISTS lessons (
    id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version > 0), topic_id TEXT NOT NULL REFERENCES curriculum_topics(id),
    status TEXT NOT NULL CHECK(status IN ('draft', 'published', 'archived')), payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY(id, version)
);

CREATE TABLE IF NOT EXISTS worked_examples (
    id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version > 0), topic_id TEXT NOT NULL REFERENCES curriculum_topics(id), family_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft', 'published', 'archived')), payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY(id, version)
);

CREATE TABLE IF NOT EXISTS content_exposures (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, student_id TEXT NOT NULL REFERENCES students(id),
    content_id TEXT NOT NULL, content_version INTEGER NOT NULL, family_id TEXT NOT NULL, kind TEXT NOT NULL,
    assessment_id TEXT, created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_curriculum_topics_course_stage_order ON curriculum_topics(course, active, stage, order_index);
CREATE INDEX IF NOT EXISTS idx_topic_prerequisites_prerequisite ON topic_prerequisites(prerequisite_topic_id);
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
CREATE INDEX IF NOT EXISTS idx_exposure_student_family ON content_exposures(student_id, family_id, kind);
CREATE INDEX IF NOT EXISTS idx_student_sessions_token_hash ON student_sessions(token_hash);

CREATE OR REPLACE FUNCTION enforce_registered_course() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM courses WHERE id = NEW.course AND active = 1) THEN
        RAISE EXCEPTION 'unregistered_course';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_curriculum_registered_course ON curriculum_topics;
CREATE TRIGGER trg_curriculum_registered_course BEFORE INSERT OR UPDATE ON curriculum_topics
FOR EACH ROW EXECUTE FUNCTION enforce_registered_course();

CREATE OR REPLACE FUNCTION prevent_required_prerequisite_cycle() RETURNS trigger AS $$
BEGIN
    IF NEW.relation_type = 'required' AND EXISTS (
        WITH RECURSIVE ancestors(id) AS (
            SELECT NEW.prerequisite_topic_id
            UNION
            SELECT prerequisite_topic_id FROM topic_prerequisites p JOIN ancestors a ON p.topic_id = a.id
            WHERE p.relation_type = 'required'
        ) SELECT 1 FROM ancestors WHERE id = NEW.topic_id
    ) THEN
        RAISE EXCEPTION 'required_prerequisite_cycle';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_required_cycle ON topic_prerequisites;
CREATE TRIGGER trg_required_cycle BEFORE INSERT OR UPDATE ON topic_prerequisites
FOR EACH ROW EXECUTE FUNCTION prevent_required_prerequisite_cycle();