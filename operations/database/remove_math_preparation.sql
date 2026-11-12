-- Remove only the legacy mathematics-preparation references in machine learning.
-- Canonical mathematics topics, other placements and learning records are retained.
DELETE FROM public.topic_placements
WHERE course_id='machine_learning' AND is_reference=1
  AND parent_group_id ~ '^math-preparation-';
