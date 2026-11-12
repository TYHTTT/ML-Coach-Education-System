-- Retire prerequisite rules and verification records without dropping study history.
DROP TABLE IF EXISTS public.prerequisite_verifications;
DROP TABLE IF EXISTS public.topic_prerequisites;
DROP FUNCTION IF EXISTS public.prevent_required_prerequisite_cycle();

ALTER TABLE public.practice_sets DROP COLUMN IF EXISTS prerequisite_for;
ALTER TABLE public.practice_sets DROP COLUMN IF EXISTS rule_version;

UPDATE public.student_topic_states SET status='not_started' WHERE status='locked';
DO $$
DECLARE constraint_name text;
BEGIN
    FOR constraint_name IN
        SELECT c.conname FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=ANY(c.conkey)
        WHERE c.conrelid='public.student_topic_states'::regclass
          AND c.contype='c' AND a.attname='status'
    LOOP
        EXECUTE format('ALTER TABLE public.student_topic_states DROP CONSTRAINT %I', constraint_name);
    END LOOP;
END;
$$;
ALTER TABLE public.student_topic_states ADD CONSTRAINT student_topic_states_status_check
CHECK (status IN ('not_started','learning','practicing','needs_remediation','ready_for_checkpoint','mastered'));
