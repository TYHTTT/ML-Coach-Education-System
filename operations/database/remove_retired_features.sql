-- Run through cleanup_retired.py to back up the database before applying.
-- Explicit targets only. Unexpected dependencies abort the transaction.
ALTER TABLE IF EXISTS public.practice_sets DROP COLUMN IF EXISTS blueprint_id;
ALTER TABLE IF EXISTS public.practice_questions
    DROP COLUMN IF EXISTS bank_item_id,
    DROP COLUMN IF EXISTS item_version,
    DROP COLUMN IF EXISTS solution_steps_json;

DROP TABLE IF EXISTS public.content_review_events;
DROP TABLE IF EXISTS public.question_bank_topics;
DROP TABLE IF EXISTS public.question_bank_items;
DROP TABLE IF EXISTS public.assessment_blueprints;
DROP TABLE IF EXISTS public.content_exposures;
DROP TABLE IF EXISTS public.worked_examples;
DROP TABLE IF EXISTS public.lessons;
DROP TABLE IF EXISTS public.document_chunks;
DROP TABLE IF EXISTS public.documents;

-- RESTRICT is intentional: other uses of pgvector must not be removed.
DROP EXTENSION IF EXISTS vector;
