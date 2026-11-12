ALTER TABLE courses ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';
ALTER TABLE courses ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0;
ALTER TABLE courses ADD COLUMN IF NOT EXISTS created_at TEXT NOT NULL DEFAULT to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"');
ALTER TABLE courses ADD COLUMN IF NOT EXISTS updated_at TEXT NOT NULL DEFAULT to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"');
ALTER TABLE courses ADD COLUMN IF NOT EXISTS deleted_at TEXT;

UPDATE courses SET description=CASE id
    WHEN 'machine_learning' THEN '模型、算法与实践'
    WHEN 'advanced_mathematics' THEN '极限、微积分与定理'
    WHEN 'linear_algebra' THEN '向量、矩阵与几何'
    WHEN 'probability_statistics' THEN '概率、分布与统计' END,
    sort_order=CASE id WHEN 'machine_learning' THEN 1 WHEN 'advanced_mathematics' THEN 2 WHEN 'linear_algebra' THEN 3 ELSE 4 END
WHERE id IN ('machine_learning','advanced_mathematics','linear_algebra','probability_statistics')
    AND description='' AND sort_order=0 AND updated_at=created_at;

DO $$
DECLARE target_table TEXT;
BEGIN
    FOREACH target_table IN ARRAY ARRAY['curriculum_topics','practice_sets','learning_sessions'] LOOP
        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', target_table, target_table || '_course_check');
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid=target_table::regclass AND conname=target_table || '_course_fkey') THEN
            EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (course) REFERENCES courses(id)', target_table, target_table || '_course_fkey');
        END IF;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION enforce_registered_course() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM courses WHERE id=NEW.course AND active=1 AND deleted_at IS NULL) THEN
        RAISE EXCEPTION 'unregistered_course';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
