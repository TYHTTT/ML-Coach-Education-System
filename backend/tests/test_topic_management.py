from pathlib import Path

import pytest

from tests.test_course_management import api, protected_api, COURSE  # noqa: F401

BASE = "/api/v1/admin/courses/physics/topics"


def values(title, **changes):
    return {"title": title, "description": "知识点简介", "stage": 1, "stage_title": "力学",
            "learning_objectives": ["理解概念"], "aliases": [], "retrieval_keywords": [],
            "difficulty": "easy", "prerequisite_ids": [], **changes}


def create(client, headers, title, **changes):
    response = client.post(BASE, headers=headers, json=values(title, **changes))
    assert response.status_code == 201, response.text
    return next(t for g in response.json()["groups"] for t in g["topics"] if t["title"] == title)["id"]


@pytest.mark.parametrize("method,suffix", [("GET", ""), ("POST", ""), ("PUT", "/physics.test"),
    ("DELETE", "/physics.test"), ("POST", "/physics.test/restore"), ("PUT", "/order"),
    ("POST", "/groups/order"), ("PATCH", "/groups/1"), ("POST", "/references"),
    ("PUT", "/references/ml.test"), ("DELETE", "/references/ml.test")])
@pytest.mark.parametrize("token", [None, "student-session"])
def test_all_topic_operations_require_admin(protected_api, method, suffix, token):
    response = protected_api.request(method, BASE + suffix, json={}, headers={"Authorization": f"Bearer {token}"} if token else {})
    assert response.status_code == 401


def test_topic_crud_order_move_and_student_sync(api):
    client, app, headers, student_headers, student = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    a = create(client, headers, "位置")
    b = create(client, headers, "速度")
    c = create(client, headers, "能量", stage=2, stage_title="能量基础")
    assert client.post("/api/v1/learning/topics/" + a + "/start", headers=student_headers).status_code == 200
    updated = client.put(BASE + "/" + a, headers=headers, json=values("位移", aliases=["位置变化"], prerequisite_ids=[]))
    assert updated.status_code == 200
    ordered = client.put(BASE + "/order", headers=headers, json={"group_id": "stage-1", "topic_ids": [b, a]})
    assert ordered.status_code == 200
    assert [t["id"] for t in ordered.json()["groups"][0]["topics"]] == [b, a]
    assert client.put(BASE + "/order", headers=headers, json={"group_id": "stage-1", "topic_ids": [a]}).status_code == 409
    assert client.put(BASE + "/order", headers=headers, json={"group_id": "stage-1", "topic_ids": [a, a]}).status_code == 422
    renamed = client.patch(BASE + "/groups/1", headers=headers, json={"title": "运动学"})
    assert renamed.status_code == 200 and renamed.json()["groups"][0]["title"] == "运动学"
    reordered = client.post(BASE + "/groups/order", headers=headers, json={"group_ids": ["stage-2", "stage-1"]})
    assert reordered.status_code == 200, reordered.text
    public = client.get("/api/v1/courses/physics/outline").json()
    assert [g["title"] for g in public["groups"]] == ["能量基础", "运动学"]
    assert [t["id"] for t in public["groups"][1]["topics"]] == [b, a]
    assert client.get("/api/v1/curriculum/topics/" + a, headers=student_headers).json()["title"] == "位移"
    moved = client.put(BASE + "/" + b, headers=headers, json=values("速度", stage=1, stage_title="能量基础"))
    assert moved.status_code == 200
    assert [t["id"] for t in moved.json()["groups"][0]["topics"]] == [c, b]
    assert client.delete(BASE + "/" + a, headers=headers).status_code == 200
    assert client.get("/api/v1/curriculum/topics/" + a, headers=student_headers).status_code == 404
    assert client.post("/api/v1/learning/topics/" + a + "/start", headers=student_headers).status_code == 404
    assert client.post("/api/v1/chat", headers=student_headers, json={"course": "physics", "topic_id": a, "message": "继续"}).status_code == 404
    with app.state.learning_repository._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM student_topic_states WHERE student_id=? AND topic_id=?", (student["id"], a)).fetchone()["n"] == 1
    restored = client.post(BASE + "/" + a + "/restore", headers=headers)
    assert restored.status_code == 200 and restored.json()["removed_topics"] == []
    assert client.get("/api/v1/curriculum/topics/" + a, headers=student_headers).status_code == 200


def test_prerequisites_cycles_and_removal_are_transactional(api):
    client, app, headers, _, _ = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    a = create(client, headers, "位置")
    b = create(client, headers, "速度", prerequisite_ids=[a])
    assert client.delete(BASE + "/" + a, headers=headers).status_code == 409
    assert client.put(BASE + "/" + a, headers=headers, json=values("不应保存", prerequisite_ids=[b])).status_code == 409
    assert client.put(BASE + "/" + a, headers=headers, json=values("不应保存", prerequisite_ids=[a])).status_code == 422
    assert client.put(BASE + "/" + a, headers=headers, json=values("不应保存", prerequisite_ids=["physics.missing"])).status_code == 422
    current = client.get(BASE, headers=headers).json()
    assert [t["title"] for t in current["groups"][0]["topics"]] == ["位置", "速度"]
    with app.state.learning_repository._connect() as connection:
        connection.execute("UPDATE topic_prerequisites SET reason='保留说明',required_mastery=0.8 WHERE topic_id=?", (b,))
        connection.execute("INSERT INTO topic_prerequisites(topic_id,prerequisite_topic_id,relation_type) VALUES (?,?,'related')", (b, a))
    assert client.put(BASE + "/" + b, headers=headers, json=values("速度", prerequisite_ids=[a])).status_code == 200
    with app.state.learning_repository._connect() as connection:
        rows = connection.execute("SELECT reason,required_mastery,relation_type FROM topic_prerequisites WHERE topic_id=?", (b,)).fetchall()
        assert len(rows) == 2
        assert next(r for r in rows if r["relation_type"] == "required")["reason"] == "保留说明"
    assert client.delete(BASE + "/" + b, headers=headers).status_code == 200
    assert client.delete(BASE + "/" + a, headers=headers).status_code == 200
    assert client.post(BASE + "/" + b + "/restore", headers=headers).status_code == 409
    assert client.post(BASE + "/" + a + "/restore", headers=headers).status_code == 200
    assert client.post(BASE + "/" + b + "/restore", headers=headers).status_code == 200


def test_cross_course_reference_preserves_owner_and_orders_with_local_nodes(api):
    client, app, headers, _, _ = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    local = create(client, headers, "速度")
    candidate = next(t for t in client.get("/api/v1/admin/topics", headers=headers).json() if t["course"] == "linear_algebra")
    ref = candidate["id"]
    reference = {"topic_id": ref, "stage": 1, "stage_title": "力学"}
    assert client.post(BASE + "/references", headers=headers, json=reference).status_code == 201
    assert client.post(BASE + "/references", headers=headers, json=reference).status_code == 409
    assert client.put(BASE + "/" + ref, headers=headers, json=values("恶意更改")).status_code == 403
    assert client.delete(BASE + "/" + ref, headers=headers).status_code == 403
    assert client.put(BASE + "/order", headers=headers, json={"group_id": "stage-1", "topic_ids": [ref, local]}).status_code == 200
    public = client.get("/api/v1/courses/physics/outline").json()
    assert len(public["groups"]) == 1 and public["groups"][0]["title"] == "力学"
    assert [t["id"] for t in public["groups"][0]["topics"]] == [ref, local]
    assert public["groups"][0]["topics"][0]["owner_course"] == "linear_algebra"
    assert client.delete(f"/api/v1/admin/courses/linear_algebra/topics/{ref}", headers=headers).status_code == 409
    assert client.put(BASE + "/references/" + ref, headers=headers, json={**reference, "stage": 2, "stage_title": "数学"}).status_code == 200
    assert client.delete(BASE + "/references/" + ref, headers=headers).status_code == 200
    with app.state.learning_repository._connect() as connection:
        assert connection.execute("SELECT title,active FROM curriculum_topics WHERE id=?", (ref,)).fetchone() == {"title": candidate["title"], "active": 1}


def test_inactive_course_can_be_compiled_and_migration_is_idempotent(api):
    client, app, headers, _, _ = api
    client.post("/api/v1/admin/courses", headers=headers, json={**COURSE, "active": False})
    a = create(client, headers, "位置")
    assert client.get("/api/v1/courses/physics/outline").status_code == 404
    script = (Path(__file__).resolve().parents[2] / "operations/database/enable_topic_management.sql").read_text(encoding="utf-8")
    with app.state.learning_repository._connect() as connection:
        before = connection.execute("SELECT * FROM curriculum_topics ORDER BY id").fetchall()
        connection.execute_script(script)
        connection.execute_script(script)
        assert before == connection.execute("SELECT * FROM curriculum_topics ORDER BY id").fetchall()
    assert client.patch("/api/v1/admin/courses/physics", headers=headers, json={"active": True}).status_code == 200
    assert client.get("/api/v1/courses/physics/outline").json()["groups"][0]["topics"][0]["id"] == a
    client.delete("/api/v1/admin/courses/physics", headers=headers)
    assert client.get(BASE, headers=headers).status_code == 404
    assert client.post(BASE, headers=headers, json=values("不能添加")).status_code == 404
