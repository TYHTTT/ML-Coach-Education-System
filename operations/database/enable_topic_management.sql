-- Administrator compilation may edit a disabled course. Student routes still
-- enforce active=1; deleted courses must not receive new curriculum changes.
CREATE OR REPLACE FUNCTION enforce_registered_course() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM courses WHERE id=NEW.course AND deleted_at IS NULL) THEN
        RAISE EXCEPTION 'unregistered_course';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
