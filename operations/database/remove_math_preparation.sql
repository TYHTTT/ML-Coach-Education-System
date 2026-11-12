-- Remove only the legacy mathematics-preparation references in machine learning.
-- Canonical mathematics topics, other placements and learning records are retained.
DELETE FROM public.topic_placements t
WHERE course_id='machine_learning'
  AND parent_group_id ~ '^math-preparation-'
  AND EXISTS (SELECT 1 FROM curriculum_topics owner WHERE owner.id=t.topic_id AND owner.course<>t.course_id);
