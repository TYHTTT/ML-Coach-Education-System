import importlib.util
from pathlib import Path
import re
from types import SimpleNamespace

import psycopg
from psycopg.rows import dict_row
import pytest

from app.core.config import Settings
from app.core.types import Course
from app.curriculum.seed import seed_curriculum
from app.services.learning_repository import LearningRepository
from app.services.learning_service import LearningService


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cleanup_retired", ROOT / "operations/database/cleanup_retired.py")
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)


def test_cleanup_sql_has_only_declared_targets_and_restricts_unknown_dependencies():
    script = cleanup.SQL_FILE.read_text(encoding="utf-8")
    assert set(re.findall(r"DROP TABLE IF EXISTS public\.(\w+)", script)) == set(cleanup.RETIRED_TABLES)
    assert "CASCADE" not in script.upper()
    assert "DELETE FROM" not in script.upper()
    assert "DROP SCHEMA" not in script.upper()
    assert "DROP EXTENSION IF EXISTS vector;" in script


def test_backup_keeps_password_out_of_command_line(monkeypatch, tmp_path):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        Path(command[-1]).write_bytes(b"PGDMP-test-archive")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cleanup.subprocess, "run", run)
    backup = cleanup._create_backup("postgresql://tester:private-key@localhost/test", tmp_path, "pg_dump")
    assert backup.is_file()
    command, kwargs = calls[0]
    assert "private-key" not in str(command)
    assert kwargs["env"]["PGPASSWORD"] == "private-key"
    assert kwargs["env"]["PGDATABASE"] == "test"
    assert "--format=custom" in command


@pytest.fixture
def legacy_database(postgres_test_database_url):
    repository = LearningRepository(postgres_test_database_url)
    seed_curriculum(repository)
    account = repository.register_student(username="cleanup_test", password="test-password", display_name="清理测试")
    repository.update_topic_state(account["id"], "ml.machine_learning_basics", status="learning")
    with psycopg.connect(postgres_test_database_url, row_factory=dict_row) as connection:
        connection.execute("""
            CREATE TABLE assessment_blueprints (id text PRIMARY KEY);
            CREATE TABLE question_bank_items (id text PRIMARY KEY);
            CREATE TABLE question_bank_topics (id text PRIMARY KEY, item_id text REFERENCES question_bank_items(id));
            CREATE TABLE content_review_events (id text PRIMARY KEY, item_id text REFERENCES question_bank_items(id));
            CREATE TABLE content_exposures (id text PRIMARY KEY);
            CREATE TABLE lessons (id text PRIMARY KEY);
            CREATE TABLE worked_examples (id text PRIMARY KEY);
            CREATE TABLE documents (id text PRIMARY KEY);
            CREATE TABLE document_chunks (id text PRIMARY KEY, document_id text REFERENCES documents(id));
            ALTER TABLE practice_sets ADD COLUMN blueprint_id text REFERENCES assessment_blueprints(id);
            ALTER TABLE practice_questions ADD COLUMN bank_item_id text, ADD COLUMN item_version integer, ADD COLUMN solution_steps_json text;
            INSERT INTO documents VALUES ('legacy-document');
            INSERT INTO document_chunks VALUES ('legacy-chunk', 'legacy-document');
            INSERT INTO question_bank_items VALUES ('legacy-question');
            INSERT INTO question_bank_topics VALUES ('legacy-link', 'legacy-question');
        """, prepare=False)
    try:
        yield postgres_test_database_url, repository, account
    finally:
        # Leave the shared dedicated test database ready for the next fixture.
        with psycopg.connect(postgres_test_database_url) as connection:
            connection.execute("DROP VIEW IF EXISTS retired_content_dependency")
            connection.execute(cleanup.SQL_FILE.read_text(encoding="utf-8"), prepare=False)


def _plan(url):
    with psycopg.connect(url, row_factory=dict_row) as connection:
        return cleanup.inspect_database(connection)


def test_preview_never_backs_up_or_modifies_data(legacy_database, monkeypatch):
    url, _, _ = legacy_database
    monkeypatch.setattr(cleanup, "_create_backup", lambda *args: pytest.fail("Preview must not run a backup"))
    before = _plan(url)
    result = cleanup.cleanup_database(url)
    assert result["plan"] == before == _plan(url)
    assert result["applied"] is False
    assert result["plan"]["tables"]["document_chunks"] == 1


def test_backup_failure_prevents_all_deletions(legacy_database, monkeypatch):
    url, _, _ = legacy_database
    before = _plan(url)

    def fail(*args):
        raise RuntimeError("Backup unavailable")

    monkeypatch.setattr(cleanup, "_create_backup", fail)
    with pytest.raises(RuntimeError, match="Backup unavailable"):
        cleanup.cleanup_database(url, apply=True)
    assert _plan(url) == before


def test_cleanup_preserves_accounts_curriculum_progress_and_current_queries(legacy_database, monkeypatch, tmp_path):
    url, repository, account = legacy_database
    backups = []

    def backup(*args):
        backups.append(args)
        return tmp_path / "test.backup"

    monkeypatch.setattr(cleanup, "_create_backup", backup)
    result = cleanup.cleanup_database(url, apply=True)
    assert result["applied"] is True
    assert result["retained_tables"] == 16
    assert _plan(url) == {"tables": {}, "columns": {}, "vector": False}
    assert repository.student_from_token(account["access_token"])["id"] == account["id"]
    assert repository.get_topic_state(account["id"], "ml.machine_learning_basics")["status"] == "learning"
    service = LearningService(settings=Settings(_env_file=None), repository=repository)
    for course in Course:
        assert service.dashboard(student_id=account["id"], course=course)["total_topics"] > 0
    assert cleanup.cleanup_database(url, apply=True)["applied"] is False
    assert len(backups) == 1


def test_unexpected_dependency_rolls_back_tables_and_column_deletions(legacy_database, monkeypatch, tmp_path):
    url, _, _ = legacy_database
    monkeypatch.setattr(cleanup, "_create_backup", lambda *args: tmp_path / "test.backup")
    with psycopg.connect(url) as connection:
        connection.execute("CREATE VIEW retired_content_dependency AS SELECT * FROM documents")
    before = _plan(url)
    with pytest.raises(psycopg.errors.DependentObjectsStillExist):
        cleanup.cleanup_database(url, apply=True)
    assert _plan(url) == before
