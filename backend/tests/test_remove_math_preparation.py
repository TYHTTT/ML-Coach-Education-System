import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import psycopg
from psycopg.rows import dict_row
import pytest

from app.api.course_content import router
from app.curriculum.seed import seed_curriculum
from app.services.learning_repository import LearningRepository

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("remove_math_preparation", ROOT / "operations/database/remove_math_preparation.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def client_for(repository):
    app = FastAPI()
    app.state.learning_repository = repository
    app.include_router(router)
    return TestClient(app)


def test_default_ml_directory_has_no_automatic_math_references(postgres_test_database_url):
    repository = LearningRepository(postgres_test_database_url)
    seed_curriculum(repository)
    client = client_for(repository)
    outline = client.get("/api/v1/courses/machine_learning/outline").json()
    assert len(outline["groups"]) == 7
    topics = [topic for group in outline["groups"] for topic in group["topics"]]
    assert len(topics) == 30 and all(t["id"].startswith("ml.") for t in topics)
    assert all("数学准备" not in group["title"] for group in outline["groups"])
    for course, count in [("advanced_mathematics", 23), ("linear_algebra", 10), ("probability_statistics", 11)]:
        math = client.get(f"/api/v1/courses/{course}/outline").json()
        assert sum(len(g["topics"]) for g in math["groups"]) == count


@pytest.fixture
def legacy_preparation(postgres_test_database_url):
    repository = LearningRepository(postgres_test_database_url)
    seed_curriculum(repository)
    student = repository.register_student(username="math_cleanup", display_name="测试", password="test-password")
    repository.update_topic_state(student["id"], "math.gradient", status="learning", evidence_count=1, mastery=0.67)
    with repository._connect() as connection:
        connection.execute("ALTER TABLE topic_placements DROP CONSTRAINT topic_placements_topic_course_fkey")
        connection.execute("ALTER TABLE topic_placements ADD COLUMN is_reference integer NOT NULL DEFAULT 0")
        connection.execute("""INSERT INTO topic_placements(course_id,topic_id,parent_group_id,group_title,order_index,is_reference) VALUES
            ('machine_learning','math.gradient','math-preparation-advanced_mathematics','数学准备 · 高等数学',1,1),
            ('machine_learning','la.vectors','math-preparation-linear_algebra','数学准备 · 线性代数',2,1),
            ('machine_learning','prob.basics','stage-8','手动编排章节',1,1),
            ('advanced_mathematics','la.vectors','math-preparation-linear_algebra','其他课程中的引用',1,1)""")
    yield postgres_test_database_url, repository, student
    with repository._connect() as connection:
        connection.execute_script((ROOT / "operations/database/remove_course_references.sql").read_text(encoding="utf-8"))


def test_migration_removes_only_legacy_ml_placements_and_does_not_reseed(legacy_preparation, monkeypatch, tmp_path):
    url, repository, student = legacy_preparation
    backups = []
    def backup(*args):
        backups.append(args)
        file = tmp_path / "test.backup"
        file.write_bytes(b"test-backup")
        return file
    monkeypatch.setattr(migration, "_create_backup", backup)
    assert migration.remove_math_preparation(url)["pending"] == 2 and not backups
    with psycopg.connect(url, row_factory=dict_row) as connection:
        before = migration.snapshot(connection)
    result = migration.remove_math_preparation(url, apply=True)
    assert result["removed"] == 2 and result["applied"] and Path(result["backup"]).is_file()
    with psycopg.connect(url, row_factory=dict_row) as connection:
        assert before == migration.snapshot(connection)
        assert connection.execute("SELECT count(*) AS n FROM curriculum_topics").fetchone()["n"] == 74
        assert connection.execute("SELECT count(*) AS n FROM topic_placements WHERE course_id='machine_learning' AND topic_id='prob.basics'").fetchone()["n"] == 1
        assert connection.execute("SELECT count(*) AS n FROM topic_placements WHERE course_id='advanced_mathematics' AND topic_id='la.vectors'").fetchone()["n"] == 1
    assert repository.get_topic_state(student["id"], "math.gradient")["mastery"] == 0.67
    seed_curriculum(repository)
    assert migration.remove_math_preparation(url, apply=True)["pending"] == 0 and len(backups) == 1
    ml = client_for(repository).get("/api/v1/courses/machine_learning/outline").json()
    assert all(not group["id"].startswith("math-preparation") for group in ml["groups"])


def test_backup_failure_prevents_math_placement_deletion(legacy_preparation, monkeypatch):
    url, _, _ = legacy_preparation
    def fail(*args): raise RuntimeError("backup unavailable")
    monkeypatch.setattr(migration, "_create_backup", fail)
    with pytest.raises(RuntimeError, match="backup unavailable"):
        migration.remove_math_preparation(url, apply=True)
    assert migration.remove_math_preparation(url)["pending"] == 2
