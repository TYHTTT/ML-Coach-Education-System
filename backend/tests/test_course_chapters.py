import importlib.util
from pathlib import Path

import pytest
import psycopg
from psycopg.rows import dict_row

from tests.test_course_management import api, protected_api, COURSE  # noqa: F401
from tests.test_topic_management import BASE, values

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("enable_course_chapters", ROOT / "operations/database/enable_course_chapters.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


@pytest.mark.parametrize("token", [None, "student-session"])
def test_create_chapter_requires_admin(protected_api, token):
    assert protected_api.post(BASE + "/groups", json={"title": "章节"}, headers={"Authorization": f"Bearer {token}"} if token else {}).status_code == 401


@pytest.mark.parametrize("title", ["", "  ", "长" * 101])
def test_create_chapter_validates_title_without_accessing_data(protected_api, title):
    assert protected_api.post(BASE + "/groups", json={"title": title}, headers={"Authorization": "Bearer admin-session"}).status_code == 422


def test_empty_chapter_persists_then_accepts_topics_and_survives_last_topic_deletion(api):
    client, app, headers, _, _ = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    created = client.post(BASE + "/groups", headers=headers, json={"title": "  第一章  "})
    assert created.status_code == 201
    assert created.json()["groups"] == [{"id": "stage-1", "stage": 1, "title": "第一章", "topics": []}]
    assert client.get(BASE, headers=headers).json()["groups"] == created.json()["groups"]
    assert client.get("/api/v1/courses/physics/outline").json()["groups"][0]["topics"] == []
    assert client.get("/api/v1/admin/courses/physics", headers=headers).json()["stage_count"] == 1
    with app.state.learning_repository._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM curriculum_topics WHERE course='physics'").fetchone()["n"] == 0
    assert client.patch(BASE + "/groups/1", headers=headers, json={"title": "改名空章节"}).status_code == 200
    second = client.post(BASE + "/groups", headers=headers, json={"title": "第二章"}).json()
    assert len(second["groups"]) == 2
    saved = client.post(BASE, headers=headers, json=values("知识点", stage=2, stage_title="第二章", existing_stage=True))
    assert saved.status_code == 201
    topic = saved.json()["groups"][1]["topics"][0]["id"]
    assert client.post(BASE + "/groups/order", headers=headers, json={"group_ids": ["stage-2", "stage-1"]}).status_code == 200
    outline = client.get(BASE, headers=headers).json()
    assert [group["title"] for group in outline["groups"]] == ["第二章", "改名空章节"]
    assert outline["groups"][0]["topics"][0]["id"] == topic
    assert client.delete(BASE + "/" + topic, headers=headers).json()["groups"][0]["topics"] == []
    deleted = client.request("DELETE", BASE + "/groups/2", headers=headers, json={"title": "改名空章节", "topic_ids": []})
    assert deleted.status_code == 200 and len(deleted.json()["groups"]) == 1
    assert client.request("DELETE", BASE + "/groups/1", headers=headers, json={"title": "第二章", "topic_ids": []}).json()["groups"] == []
    # An editor opened before chapter deletion cannot recreate the deleted chapter.
    assert client.post(BASE, headers=headers, json=values("过期编辑器", stage_title="第二章", existing_stage=True)).status_code == 409


def test_empty_confirmation_cannot_delete_a_populated_chapter(api):
    client, _, headers, _, _ = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    client.post(BASE, headers=headers, json=values("知识点"))
    assert client.request("DELETE", BASE + "/groups/1", headers=headers, json={"title": "力学", "topic_ids": []}).status_code == 409


def test_chapter_migration_backfills_only_owned_chapters_and_preserves_existing_data(api, monkeypatch, tmp_path):
    client, app, headers, _, _ = api
    url = app.state.settings.database_url
    with psycopg.connect(url, row_factory=dict_row) as connection:
        connection.execute("DROP TABLE course_chapters")
        before = migration._retained_snapshot(connection)
    def backup(*args):
        archive = tmp_path / "backup"; archive.write_bytes(b"backup"); return archive
    monkeypatch.setattr(migration, "_create_backup", backup)
    assert migration.enable_course_chapters(url)["retained_tables"] == 15
    with psycopg.connect(url, row_factory=dict_row) as connection:
        after = migration._retained_snapshot(connection)
        assert before == {name: after[name] for name in before}
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    assert client.post(BASE + "/groups", headers=headers, json={"title": "独立空章节"}).status_code == 201
    with psycopg.connect(url, row_factory=dict_row) as connection: before = migration._retained_snapshot(connection)
    assert migration.enable_course_chapters(url)["retained_tables"] == 16
    with psycopg.connect(url, row_factory=dict_row) as connection: assert migration._retained_snapshot(connection) == before
