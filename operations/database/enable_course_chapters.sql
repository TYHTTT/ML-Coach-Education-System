CREATE TABLE IF NOT EXISTS course_chapters (
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    stage INTEGER NOT NULL CHECK (stage > 0),
    title TEXT NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 100),
    PRIMARY KEY(course_id, stage)
);

INSERT INTO course_chapters(course_id,stage,title)
SELECT p.course_id,substring(p.parent_group_id FROM 7)::integer,min(p.group_title)
FROM topic_placements p JOIN curriculum_topics t ON t.id=p.topic_id AND t.course=p.course_id
WHERE p.parent_group_id ~ '^stage-[1-9][0-9]*$'
GROUP BY p.course_id,p.parent_group_id
ON CONFLICT DO NOTHING;
