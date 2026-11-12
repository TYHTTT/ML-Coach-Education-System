-- Retire all cross-course placements while preserving canonical topics and history.
DELETE FROM public.topic_placements p
USING public.curriculum_topics t
WHERE t.id=p.topic_id AND t.course<>p.course_id;

ALTER TABLE public.topic_placements DROP COLUMN IF EXISTS is_reference;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
        WHERE conrelid='public.curriculum_topics'::regclass AND conname='curriculum_topics_id_course_key') THEN
        ALTER TABLE public.curriculum_topics ADD CONSTRAINT curriculum_topics_id_course_key UNIQUE(id, course);
    END IF;
END;
$$;

ALTER TABLE public.topic_placements DROP CONSTRAINT IF EXISTS topic_placements_topic_id_fkey;
ALTER TABLE public.topic_placements DROP CONSTRAINT IF EXISTS topic_placements_topic_course_fkey;
ALTER TABLE public.topic_placements ADD CONSTRAINT topic_placements_topic_course_fkey
    FOREIGN KEY(topic_id, course_id) REFERENCES public.curriculum_topics(id, course);
