from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.exceptions import AdminUnauthorizedError
from app.curriculum.models import CurriculumSeed
from app.main import create_app
from tests.mocks import MockLLMClient


AUTHCODE = "test-course-admin-code"
COURSE = {"id": "physics", "title": "物理学", "description": "力学与运动", "active": True, "sort_order": 5}


class Admins:
    def from_token(self, token):
        if token != "admin-session": raise AdminUnauthorizedError()
        return {"id": "admin"}


class NoCourses:
    def __getattr__(self, name):
        raise AssertionError("Course data must not be accessed before authentication/validation")


@pytest.fixture
def protected_api(monkeypatch):
    monkeypatch.setattr("app.main.seed_curriculum", lambda repository, **kwargs: None)
    app = create_app(Settings(_env_file=None), learning_repository=object(), admin_repository=Admins(),
                     course_repository=NoCourses(), llm_client=MockLLMClient())
    with TestClient(app) as client: yield client


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/v1/admin/courses"), ("POST", "/api/v1/admin/courses"),
    ("GET", "/api/v1/admin/courses/physics"), ("PATCH", "/api/v1/admin/courses/physics"),
    ("DELETE", "/api/v1/admin/courses/physics"),
])
@pytest.mark.parametrize("token", [None, "student-session", "expired-admin-session"])
def test_course_management_requires_admin_on_every_route(protected_api, method, path, token):
    response = protected_api.request(method, path, headers={"Authorization": f"Bearer {token}"} if token else {}, json=COURSE)
    assert response.status_code == 401


@pytest.mark.parametrize("changes", [{"id": "../unsafe"}, {"id": "INVALID"}, {"title": " "}, {"title": "x" * 101}, {"sort_order": -1}, {"description": "x" * 1001}])
def test_course_create_rejects_invalid_fields_before_writing(protected_api, changes):
    assert protected_api.post("/api/v1/admin/courses", headers={"Authorization": "Bearer admin-session"}, json={**COURSE, **changes}).status_code == 422


@pytest.mark.parametrize("payload", [{}, {"title": None}, {"active": None}, {"id": "renamed"}, {"title": " "}])
def test_patch_rejects_empty_null_and_identifier_changes(protected_api, payload):
    assert protected_api.patch("/api/v1/admin/courses/physics", headers={"Authorization": "Bearer admin-session"}, json=payload).status_code == 422


@pytest.fixture
def api(postgres_test_database_url):
    settings = Settings(_env_file=None, database_url=postgres_test_database_url, admin_authcode=AUTHCODE)
    app = create_app(settings, llm_client=MockLLMClient())
    with TestClient(app) as client:
        admin = client.post("/api/v1/admins/register", json={"username": "course_admin", "password": "test-password", "display_name": "课程管理员", "authcode": AUTHCODE}).json()
        student = app.state.learning_repository.register_student(username="course_student", password="test-password", display_name="课程学生")
        yield client, app, {"Authorization": "Bearer " + admin["access_token"]}, {"Authorization": "Bearer " + student["access_token"]}, student


def test_course_crud_public_visibility_empty_outline_and_filters(api):
    client, app, headers, student_headers, _ = api
    created = client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    assert created.status_code == 201
    assert created.json()["id"] == "physics" and created.json()["active"] is True
    assert client.post("/api/v1/admin/courses", headers=headers, json=COURSE).status_code == 409
    detail = client.get("/api/v1/admin/courses/physics", headers=headers).json()
    assert detail["topics"] == []
    assert any(row["id"] == "physics" for row in client.get("/api/v1/courses").json())
    listing = client.get("/api/v1/admin/courses?q=物理&page_size=1", headers=headers).json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == "physics"
    changed = client.patch("/api/v1/admin/courses/physics", headers=headers, json={"title": "基础物理", "description": "新简介", "active": False, "sort_order": 9})
    assert changed.status_code == 200 and changed.json()["title"] == "基础物理"
    assert not any(row["id"] == "physics" for row in client.get("/api/v1/courses").json())
    assert client.get("/api/v1/courses/physics/outline").status_code == 404
    assert client.get("/api/v1/admin/courses?status=inactive", headers=headers).json()["total"] == 1
    assert client.patch("/api/v1/admin/courses/physics", headers=headers, json={"active": True}).status_code == 200
    outline = client.get("/api/v1/courses/physics/outline").json()
    assert outline["title"] == "基础物理" and outline["groups"] == []
    dashboard = client.get("/api/v1/learning/dashboard?course=physics", headers=student_headers)
    assert dashboard.status_code == 200 and dashboard.json()["total_topics"] == 0
    assert dashboard.json()["next_action"] != "course_completed"
    assert client.delete("/api/v1/admin/courses/physics", headers=headers).status_code == 204
    assert client.get("/api/v1/admin/courses/physics", headers=headers).status_code == 404
    assert client.delete("/api/v1/admin/courses/physics", headers=headers).status_code == 404
    assert client.post("/api/v1/admin/courses", headers=headers, json=COURSE).status_code == 409
    with app.state.learning_repository._connect() as connection:
        assert connection.execute("SELECT deleted_at FROM courses WHERE id='physics'").fetchone()["deleted_at"]


def test_dynamic_course_topics_can_be_studied_and_delete_preserves_records(api):
    client, app, headers, student_headers, student = api
    assert client.post("/api/v1/admin/courses", headers=headers, json=COURSE).status_code == 201
    seed = CurriculumSeed.model_validate({"course": "physics", "topics": [{
        "id": "physics.motion", "slug": "motion", "title": "运动", "stage": 1, "stage_title": "力学", "order_index": 1,
        "description": "运动基础", "learning_objectives": ["理解速度"], "aliases": [], "retrieval_keywords": ["速度"],
        "difficulty": "easy", "required_dimensions": ["concept"],
    }]})
    app.state.learning_repository.upsert_curriculum([seed])
    assert client.post("/api/v1/learning/topics/physics.motion/start", headers=student_headers).status_code == 200
    response = client.post("/api/v1/chat", headers=student_headers, json={"course": "physics", "topic_id": "physics.motion", "learning_mode": "topic_teaching", "message": "当前课程是物理学，我要开始学习运动"})
    assert response.status_code == 200 and response.json()["course"] == "physics"
    assert client.get("/api/v1/admin/courses/physics", headers=headers).json()["topic_count"] == 1
    assert client.delete("/api/v1/admin/courses/physics", headers=headers).status_code == 204
    assert client.get("/api/v1/curriculum/topics/physics.motion", headers=student_headers).status_code == 404
    assert client.post("/api/v1/learning/topics/physics.motion/start", headers=student_headers).status_code == 404
    assert client.post("/api/v1/chat", headers=student_headers, json={"course": "physics", "topic_id": "physics.motion", "message": "继续学习"}).status_code == 404
    with app.state.learning_repository._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM curriculum_topics WHERE course='physics'").fetchone()["n"] == 1
        assert connection.execute("SELECT count(*) AS n FROM student_topic_states WHERE topic_id='physics.motion' AND student_id=?", (student["id"],)).fetchone()["n"] == 1
        assert connection.execute("SELECT count(*) AS n FROM learning_sessions WHERE course='physics'").fetchone()["n"] >= 1


def test_deleted_seed_course_is_not_restored_by_restart_or_schema_initialization(api):
    client, app, headers, _, _ = api
    assert client.patch("/api/v1/admin/courses/machine_learning", headers=headers, json={"title": "我的机器学习", "description": "自定义简介"}).status_code == 200
    assert client.delete("/api/v1/admin/courses/advanced_mathematics", headers=headers).status_code == 204
    with TestClient(app) as restarted:
        courses = restarted.get("/api/v1/courses").json()
        assert any(course["title"] == "我的机器学习" for course in courses)
        assert all(course["id"] != "advanced_mathematics" for course in courses)
        ml = restarted.get("/api/v1/courses/machine_learning/outline").json()
        assert all(topic["owner_course"] != "advanced_mathematics" for group in ml["groups"] for topic in group["topics"])
    root = Path(__file__).resolve().parents[2]
    with app.state.learning_repository._connect() as connection:
        connection.execute_script((root / "operations/database/initialize_postgresql.sql").read_text(encoding="utf-8"))
        assert connection.execute("SELECT deleted_at FROM courses WHERE id='advanced_mathematics'").fetchone()["deleted_at"]


def test_legacy_constraints_are_migrated_and_repeat_migration_preserves_edits(api):
    _, app, _, _, _ = api
    root = Path(__file__).resolve().parents[2]
    migration = (root / "operations/database/enable_course_management.sql").read_text(encoding="utf-8")
    with app.state.learning_repository._connect() as connection:
        connection.execute("ALTER TABLE courses DROP COLUMN description, DROP COLUMN sort_order, DROP COLUMN created_at, DROP COLUMN updated_at, DROP COLUMN deleted_at")
        connection.execute("ALTER TABLE curriculum_topics DROP CONSTRAINT curriculum_topics_course_fkey")
        connection.execute("ALTER TABLE curriculum_topics ADD CONSTRAINT curriculum_topics_course_check CHECK (course IN ('machine_learning','advanced_mathematics','linear_algebra','probability_statistics'))")
        connection.execute_script(migration)
    app.state.course_repository.update("machine_learning", {"title": "自定义课程名", "description": "", "sort_order": 0})
    with app.state.learning_repository._connect() as connection:
        connection.execute_script(migration)
    updated = app.state.course_repository.get("machine_learning")
    assert updated["title"] == "自定义课程名" and updated["description"] == "" and updated["sort_order"] == 0
    app.state.course_repository.create(COURSE)
