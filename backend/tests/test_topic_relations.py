from pathlib import Path
import importlib.util

import psycopg
from psycopg.rows import dict_row
import pytest

from tests.test_course_management import api, protected_api, COURSE  # noqa: F401
from tests.test_topic_management import BASE, create, values

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("enable_topic_relations", ROOT / "operations/database/enable_topic_relations.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def point(client, headers, topic_id, course="physics"):
    outline = client.get(f"/api/v1/admin/courses/{course}/topics", headers=headers).json()
    return next(t for group in outline["groups"] for t in group["topics"] if t["id"] == topic_id)


@pytest.mark.parametrize("token", [None, "student-session"])
def test_related_candidates_require_an_administrator(protected_api, token):
    response = protected_api.get("/api/v1/admin/related-topics", headers={"Authorization": f"Bearer {token}"} if token else {})
    assert response.status_code == 401


def test_related_topics_are_symmetric_and_do_not_change_course_directories(api):
    client, app, headers, _, _ = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    a = create(client, headers, "位置")
    b = create(client, headers, "速度")
    result = client.put(BASE + "/" + a, headers=headers, json=values("位置", related_topic_ids=[b, "la.vectors"]))
    assert result.status_code == 200, result.text
    assert set(point(client, headers, a)["related_topic_ids"]) == {b, "la.vectors"}
    assert point(client, headers, b)["related_topic_ids"] == [a]
    assert point(client, headers, "la.vectors", "linear_algebra")["related_topic_ids"] == [a]
    assert point(client, headers, a)["related_topics"][0]["course_title"]
    public = client.get("/api/v1/courses/physics/outline").json()
    assert {t["id"] for g in public["groups"] for t in g["topics"]} == {a, b}
    with app.state.learning_repository._connect() as connection:
        before = connection.execute("SELECT * FROM topic_relations ORDER BY topic_a_id,topic_b_id").fetchall()
        assert len(before) == 2
        assert connection.execute("SELECT count(*) AS n FROM topic_placements p JOIN curriculum_topics t ON t.id=p.topic_id WHERE t.course<>p.course_id").fetchone()["n"] == 0
    # Older clients editing only metadata do not erase graph edges.
    assert client.put(BASE + "/" + a, headers=headers, json=values("位置改名")).status_code == 200
    with app.state.learning_repository._connect() as connection:
        assert before == connection.execute("SELECT * FROM topic_relations ORDER BY topic_a_id,topic_b_id").fetchall()
    # Saving the same pair from its other endpoint is not a second edge.
    target = point(client, headers, "la.vectors", "linear_algebra")
    payload = values(target["title"], stage=target["stage"], stage_title=target["stage_title"], related_topic_ids=[a])
    assert client.put("/api/v1/admin/courses/linear_algebra/topics/la.vectors", headers=headers, json=payload).status_code == 200
    with app.state.learning_repository._connect() as connection:
        assert before == connection.execute("SELECT * FROM topic_relations ORDER BY topic_a_id,topic_b_id").fetchall()
    assert client.put(BASE + "/" + b, headers=headers, json=values("速度", related_topic_ids=[])).status_code == 200
    assert point(client, headers, a)["related_topic_ids"] == ["la.vectors"]


def test_relation_validation_rolls_back_metadata_and_new_topics(api):
    client, app, headers, _, _ = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    a = create(client, headers, "位置")
    b = create(client, headers, "速度")
    for ids in ([a], [b, b], ["physics.missing"], ["invalid"]):
        response = client.put(BASE + "/" + a, headers=headers, json=values("不应保存", stage=2, stage_title="不应出现", related_topic_ids=ids))
        assert response.status_code == 422
    assert point(client, headers, a)["title"] == "位置"
    assert len(client.get(BASE, headers=headers).json()["groups"]) == 1
    assert client.post(BASE, headers=headers, json=values("不应创建", related_topic_ids=["physics.missing"])).status_code == 422
    with app.state.learning_repository._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM curriculum_topics WHERE course='physics'").fetchone()["n"] == 2
    # Relatedness is not a prerequisite graph: cycles are valid.
    c = create(client, headers, "加速度", related_topic_ids=[a, b])
    assert client.put(BASE + "/" + a, headers=headers, json=values("位置", related_topic_ids=[b, c])).status_code == 200
    with app.state.learning_repository._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM topic_relations").fetchone()["n"] == 3
    with pytest.raises(psycopg.errors.CheckViolation):
        with app.state.learning_repository._connect() as connection:
            connection.execute("INSERT INTO topic_relations(topic_a_id,topic_b_id) VALUES (?,?)", (a, a))


def test_removed_related_points_are_preserved_but_cannot_be_newly_selected(api):
    client, _, headers, _, _ = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    a = create(client, headers, "位置")
    b = create(client, headers, "速度", related_topic_ids=[a])
    assert client.delete(BASE + "/" + b, headers=headers).status_code == 200
    related = point(client, headers, a)["related_topics"][0]
    assert related["id"] == b and related["available"] is False
    assert client.put(BASE + "/" + a, headers=headers, json=values("位置", related_topic_ids=[b])).status_code == 200
    assert client.put(BASE + "/" + a, headers=headers, json=values("位置", related_topic_ids=[])).status_code == 200
    assert client.put(BASE + "/" + a, headers=headers, json=values("位置", related_topic_ids=[b])).status_code == 422
    assert client.post(BASE + "/" + b + "/restore", headers=headers).status_code == 200
    assert client.put(BASE + "/" + a, headers=headers, json=values("位置", related_topic_ids=[b, "la.vectors"])).status_code == 200
    assert client.delete("/api/v1/admin/courses/linear_algebra", headers=headers).status_code == 204
    assert next(t for t in point(client, headers, a)["related_topics"] if t["id"] == "la.vectors")["available"] is False
    assert client.put(BASE + "/" + a, headers=headers, json=values("位置", related_topic_ids=[b, "la.vectors"])).status_code == 200


def test_related_candidates_support_cross_course_search_paging_and_exclusion(api):
    client, _, headers, _, _ = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    a = create(client, headers, "测试知识点")
    endpoint = "/api/v1/admin/related-topics"
    result = client.get(endpoint, headers=headers, params={"q": "测试知识点", "course_id": "physics"}).json()
    assert result["total"] == 1 and result["items"][0]["id"] == a
    assert client.get(endpoint, headers=headers, params={"course_id": "physics", "exclude_topic_id": a}).json()["total"] == 0
    first = client.get(endpoint, headers=headers, params={"page_size": 1}).json()
    second = client.get(endpoint, headers=headers, params={"page_size": 1, "page": 2}).json()
    assert first["total"] == 75 and first["items"][0]["id"] != second["items"][0]["id"]
    assert client.patch("/api/v1/admin/courses/linear_algebra", headers=headers, json={"active": False}).status_code == 200
    candidate = client.get(endpoint, headers=headers, params={"q": "la.vectors", "course_id": "linear_algebra"}).json()["items"][0]
    assert candidate["course_active"] is False
    client.delete(BASE + "/" + a, headers=headers)
    assert client.get(endpoint, headers=headers, params={"course_id": "physics"}).json()["total"] == 0
    client.delete("/api/v1/admin/courses/linear_algebra", headers=headers)
    assert client.get(endpoint, headers=headers, params={"course_id": "linear_algebra"}).json()["total"] == 0
    assert client.get(endpoint, headers=headers, params={"page_size": 101}).status_code == 422


def test_relation_schema_migration_preserves_old_rows_and_existing_edges(api, monkeypatch, tmp_path):
    client, app, headers, _, _ = api
    url = app.state.learning_repository.database.database_url
    archive = tmp_path / "test.backup"
    def backup(*args): archive.write_bytes(b"test-backup"); return archive
    monkeypatch.setattr(migration, "_create_backup", backup)
    with app.state.learning_repository._connect() as connection:
        connection.execute("DROP TABLE topic_relations")
    assert migration.enable_topic_relations(url)["retained_tables"] == 14
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    a = create(client, headers, "位置", related_topic_ids=["la.vectors"])
    with psycopg.connect(url, row_factory=dict_row) as connection:
        before = migration._retained_snapshot(connection)
    assert migration.enable_topic_relations(url)["retained_tables"] == 15
    with psycopg.connect(url, row_factory=dict_row) as connection:
        assert migration._retained_snapshot(connection) == before
    assert point(client, headers, a)["related_topic_ids"] == ["la.vectors"]
