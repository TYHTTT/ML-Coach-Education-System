import importlib.util
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
import pytest

from app.curriculum.seed import seed_curriculum
from app.services.learning_repository import LearningRepository

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("remove_prerequisites", ROOT / "operations/database/remove_prerequisites.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


@pytest.fixture
def legacy_database(postgres_test_database_url):
    repository = LearningRepository(postgres_test_database_url)
    seed_curriculum(repository)
    student = repository.register_student(username="remove_rules", password="test-password", display_name="迁移测试")
    repository.update_topic_state(student["id"], "ml.linear_regression", status="learning", evidence_count=2, mastery=0.65)
    with psycopg.connect(postgres_test_database_url, row_factory=dict_row) as connection:
        connection.execute("""
            ALTER TABLE student_topic_states DROP CONSTRAINT student_topic_states_status_check;
            ALTER TABLE student_topic_states ADD CHECK (status IN ('locked','not_started','learning','practicing','needs_remediation','ready_for_checkpoint','mastered'));
            ALTER TABLE practice_sets ADD COLUMN prerequisite_for text REFERENCES curriculum_topics(id), ADD COLUMN rule_version text NOT NULL DEFAULT 'legacy';
            CREATE TABLE topic_prerequisites (topic_id text REFERENCES curriculum_topics(id), prerequisite_topic_id text REFERENCES curriculum_topics(id), PRIMARY KEY(topic_id,prerequisite_topic_id));
            CREATE FUNCTION prevent_required_prerequisite_cycle() RETURNS trigger AS $$ BEGIN RETURN NEW; END; $$ LANGUAGE plpgsql;
            CREATE TRIGGER trg_required_cycle BEFORE INSERT ON topic_prerequisites FOR EACH ROW EXECUTE FUNCTION prevent_required_prerequisite_cycle();
            CREATE TABLE prerequisite_verifications (student_id text REFERENCES students(id), prerequisite_topic_id text REFERENCES curriculum_topics(id), assessment_id text REFERENCES practice_sets(id));
            INSERT INTO topic_prerequisites VALUES ('ml.linear_regression','la.dot_product');
        """, prepare=False)
        connection.execute("""INSERT INTO student_topic_states(student_id,topic_id,status,updated_at) VALUES (%s,'ml.logistic_regression','locked','migration-test')""", (student["id"],))
        connection.execute("""INSERT INTO practice_sets(id,student_id,topic_id,course,mode,status,requested_difficulty,source_snapshot_json,created_at,prerequisite_for,rule_version)
            VALUES ('history-preserved',%s,'la.dot_product','linear_algebra','practice','submitted','easy','[]','now','ml.linear_regression','old-rule')""", (student["id"],))
        connection.execute("INSERT INTO prerequisite_verifications VALUES (%s,'la.dot_product','history-preserved')", (student["id"],))
    yield postgres_test_database_url, repository, student
    with psycopg.connect(postgres_test_database_url) as connection:
        connection.execute("DROP TABLE IF EXISTS custom_relation")
        connection.execute(migration.SQL_FILE.read_text(encoding="utf-8"), prepare=False)


def backup_stub(monkeypatch, tmp_path):
    calls = []
    def backup(*args):
        calls.append(args)
        file = tmp_path / f"backup-{len(calls)}.backup"
        file.write_bytes(b"test-backup")
        return file
    monkeypatch.setattr(migration, "_create_backup", backup)
    return calls


def test_migration_is_backed_up_idempotent_and_preserves_learning_data(legacy_database, monkeypatch, tmp_path):
    url, repository, student = legacy_database
    calls = backup_stub(monkeypatch, tmp_path)
    plan = migration.remove_prerequisites(url)
    assert not plan["applied"] and not calls
    assert plan["plan"] == {"tables": ["prerequisite_verifications", "topic_prerequisites"], "columns": ["prerequisite_for", "rule_version"], "locked_states": 1}
    with psycopg.connect(url, row_factory=dict_row) as connection:
        before = migration.retained_snapshot(connection)
    result = migration.remove_prerequisites(url, apply=True)
    assert result["applied"] and Path(result["backup"]).is_file() and len(calls) == 1
    assert repository.get_topic_state(student["id"], "ml.logistic_regression")["status"] == "not_started"
    assert repository.get_topic_state(student["id"], "ml.linear_regression")["evidence_count"] == 2
    with psycopg.connect(url, row_factory=dict_row) as connection:
        assert migration.retained_snapshot(connection) == before
        assert not any(migration.inspect(connection).values())
        assert connection.execute("SELECT to_regprocedure('public.prevent_required_prerequisite_cycle()') AS name").fetchone()["name"] is None
        assert connection.execute("SELECT id FROM practice_sets").fetchone()["id"] == "history-preserved"
    migration.remove_prerequisites(url, apply=True)
    with repository._connect() as connection:
        connection.execute_script((ROOT / "operations/database/initialize_postgresql.sql").read_text(encoding="utf-8"))
    seed_curriculum(repository)
    with psycopg.connect(url, row_factory=dict_row) as connection:
        assert not any(migration.inspect(connection).values())
        assert len(migration.retained_snapshot(connection)) == 15


def test_backup_failure_leaves_all_settings_and_state_unchanged(legacy_database, monkeypatch):
    url, _, _ = legacy_database
    def fail(*args): raise RuntimeError("backup unavailable")
    monkeypatch.setattr(migration, "_create_backup", fail)
    with pytest.raises(RuntimeError, match="backup unavailable"):
        migration.remove_prerequisites(url, apply=True)
    assert migration.remove_prerequisites(url)["plan"]["locked_states"] == 1


def test_unknown_dependency_rolls_back_the_entire_migration(legacy_database, monkeypatch, tmp_path):
    url, _, _ = legacy_database
    backup_stub(monkeypatch, tmp_path)
    with psycopg.connect(url) as connection:
        connection.execute("CREATE TABLE custom_relation (topic_id text, prerequisite_topic_id text, FOREIGN KEY(topic_id,prerequisite_topic_id) REFERENCES topic_prerequisites(topic_id,prerequisite_topic_id))")
    with pytest.raises(psycopg.errors.DependentObjectsStillExist):
        migration.remove_prerequisites(url, apply=True)
    plan = migration.remove_prerequisites(url)["plan"]
    assert len(plan["tables"]) == 2 and len(plan["columns"]) == 2 and plan["locked_states"] == 1
