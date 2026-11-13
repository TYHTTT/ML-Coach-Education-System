import importlib.util
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
import pytest

from app.curriculum.seed import seed_curriculum
from app.services.learning_repository import LearningRepository

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("remove_course_references", ROOT / "operations/database/remove_course_references.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


@pytest.fixture
def legacy_references(postgres_test_database_url):
    repository = LearningRepository(postgres_test_database_url)
    seed_curriculum(repository)
    student = repository.register_student(username="reference_cleanup", password="test-password", display_name="清理测试")
    repository.update_topic_state(student["id"], "math.gradient", status="learning", evidence_count=1, mastery=0.67)
    with repository._connect() as connection:
        connection.execute("""ALTER TABLE topic_placements DROP CONSTRAINT topic_placements_topic_course_fkey;
            ALTER TABLE curriculum_topics DROP CONSTRAINT curriculum_topics_id_course_key;
            ALTER TABLE topic_placements ADD CONSTRAINT topic_placements_topic_id_fkey FOREIGN KEY(topic_id) REFERENCES curriculum_topics(id);
            ALTER TABLE topic_placements ADD COLUMN is_reference integer NOT NULL DEFAULT 0;
            INSERT INTO topic_placements(course_id,topic_id,parent_group_id,group_title,order_index,is_reference) VALUES
            ('machine_learning','math.gradient','stage-1','机器学习基础',31,1),
            ('machine_learning','la.vectors','stage-1','机器学习基础',32,0),
            ('advanced_mathematics','prob.basics','stage-1','函数与极限',24,1);
            UPDATE topic_placements SET is_reference=1 WHERE course_id='machine_learning' AND topic_id='ml.machine_learning_basics';
            UPDATE courses SET active=0 WHERE id='linear_algebra';""")
    yield postgres_test_database_url, repository, student
    with repository._connect() as connection:
        connection.execute("DROP VIEW IF EXISTS reference_flag_view")
        connection.execute_script(migration.SQL_FILE.read_text(encoding="utf-8"))


def backup_stub(monkeypatch, tmp_path):
    calls = []
    def backup(*args):
        calls.append(args)
        file = tmp_path / "test.backup"
        file.write_bytes(b"test-backup")
        return file
    monkeypatch.setattr(migration, "_create_backup", backup)
    return calls


def test_migration_removes_all_foreign_placements_and_keeps_topics_history_and_own_layout(legacy_references, monkeypatch, tmp_path):
    url, repository, student = legacy_references
    backups = backup_stub(monkeypatch, tmp_path)
    assert migration.remove_course_references(url)["plan"] == {"pending": 3, "reference_column": True, "ownership_constraint": False}
    assert not backups
    with psycopg.connect(url, row_factory=dict_row) as connection:
        before = migration.snapshot(connection)
    result = migration.remove_course_references(url, apply=True)
    assert result["applied"] and Path(result["backup"]).is_file() and result["retained_tables"] == 15
    with psycopg.connect(url, row_factory=dict_row) as connection:
        assert migration.snapshot(connection) == before
        assert migration.inspect(connection) == {"pending": 0, "reference_column": False, "ownership_constraint": True}
        assert connection.execute("SELECT count(*) AS n FROM curriculum_topics").fetchone()["n"] == 74
        assert connection.execute("SELECT count(*) AS n FROM topic_placements").fetchone()["n"] == 74
    assert repository.get_topic_state(student["id"], "math.gradient")["mastery"] == 0.67
    assert not migration.remove_course_references(url, apply=True)["applied"] and len(backups) == 1
    with repository._connect() as connection:
        connection.execute_script((ROOT / "operations/database/initialize_postgresql.sql").read_text(encoding="utf-8"))
    # Existing initialization cannot recreate the removed column or allow references.
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with repository._connect() as connection:
            connection.execute("INSERT INTO topic_placements(course_id,topic_id,parent_group_id,group_title,order_index) VALUES ('machine_learning','math.gradient','stage-1','机器学习基础',31)")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with repository._connect() as connection:
            connection.execute("UPDATE topic_placements SET course_id='advanced_mathematics' WHERE topic_id='ml.machine_learning_basics'")


def test_backup_failure_preserves_references_and_schema(legacy_references, monkeypatch):
    url, _, _ = legacy_references
    def fail(*args): raise RuntimeError("backup unavailable")
    monkeypatch.setattr(migration, "_create_backup", fail)
    with pytest.raises(RuntimeError, match="backup unavailable"):
        migration.remove_course_references(url, apply=True)
    assert migration.remove_course_references(url)["plan"]["pending"] == 3


def test_unknown_column_dependency_rolls_back_reference_deletions(legacy_references, monkeypatch, tmp_path):
    url, repository, _ = legacy_references
    backup_stub(monkeypatch, tmp_path)
    with repository._connect() as connection:
        connection.execute("CREATE VIEW reference_flag_view AS SELECT is_reference FROM topic_placements")
    with pytest.raises(psycopg.errors.DependentObjectsStillExist):
        migration.remove_course_references(url, apply=True)
    assert migration.remove_course_references(url)["plan"] == {"pending": 3, "reference_column": True, "ownership_constraint": False}
