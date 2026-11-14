from pathlib import Path

import pytest

from tests.test_course_management import api, protected_api, COURSE  # noqa: F401

BASE = "/api/v1/admin/courses/physics/topics"


def values(title, **changes):
    return {"title": title, "description": "知识点简介", "stage": 1, "stage_title": "力学",
            "learning_objectives": ["理解概念"], "aliases": [], "retrieval_keywords": [],
            "difficulty": "easy", **changes}


def create(client, headers, title, **changes):
    response = client.post(BASE, headers=headers, json=values(title, **changes))
    assert response.status_code == 201, response.text
    return next(t for g in response.json()["groups"] for t in g["topics"] if t["title"] == title)["id"]


@pytest.mark.parametrize("method,suffix", [("GET", ""), ("POST", ""), ("PUT", "/physics.test"),
    ("DELETE", "/physics.test"), ("PUT", "/order"),
    ("POST", "/groups/order"), ("PATCH", "/groups/1")])
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
    updated = client.put(BASE + "/" + a, headers=headers, json=values("位移", aliases=["位置变化"]))
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
        assert connection.execute("SELECT count(*) AS n FROM student_topic_states WHERE student_id=? AND topic_id=?", (student["id"], a)).fetchone()["n"] == 0
        assert connection.execute("SELECT count(*) AS n FROM curriculum_topics WHERE id=?", (a,)).fetchone()["n"] == 0
    assert client.post(BASE + "/" + a + "/restore", headers=headers).status_code == 404
    assert client.delete(BASE + "/" + a, headers=headers).status_code == 404






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


def test_topics_have_no_prerequisite_settings_or_learning_restrictions(api):
    client, app, headers, student_headers, _ = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    a = create(client, headers, "位置")
    b = create(client, headers, "速度")
    rejected = client.put(BASE + "/" + b, headers=headers, json=values("速度", prerequisite_ids=[a]))
    assert rejected.status_code == 422
    assert client.post("/api/v1/learning/topics/" + b + "/start", headers=student_headers).status_code == 200
    assert client.delete(BASE + "/" + a, headers=headers).status_code == 200
    detail = client.get("/api/v1/curriculum/topics/" + b, headers=student_headers).json()
    assert not {"prerequisites", "locked_reason"} & detail.keys()
    outline = client.get("/api/v1/courses/physics/outline", headers=student_headers).json()
    assert "prerequisite_gap" not in outline["groups"][0]["topics"][0]
    dashboard = client.get("/api/v1/learning/dashboard?course=physics", headers=student_headers).json()
    assert "locked_count" not in dashboard
    assert "unmet_prerequisites" not in dashboard["current_topic"]
    assert client.delete("/api/v1/admin/courses/machine_learning/topics/ml.linear_regression", headers=headers).status_code == 200


def test_cross_course_reference_endpoints_and_fields_are_removed(api):
    client, app, headers, _, _ = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    topic_id = create(client, headers, "位置")
    assert client.get("/api/v1/admin/topics", headers=headers).status_code == 404
    for method, suffix in [("POST", "/references"), ("PUT", "/references/la.vectors"), ("DELETE", "/references/la.vectors")]:
        response = client.request(method, BASE + suffix, headers=headers, json={"topic_id": "la.vectors", "stage": 1, "stage_title": "力学"})
        assert response.status_code in (404, 405)
    assert client.put(BASE + "/la.vectors", headers=headers, json=values("恶意修改")).status_code == 403
    assert client.delete(BASE + "/la.vectors", headers=headers).status_code == 403
    assert client.post(BASE + "/la.vectors/restore", headers=headers).status_code == 404
    assert client.put(BASE + "/order", headers=headers, json={"group_id": "stage-1", "topic_ids": [topic_id, "la.vectors"]}).status_code == 409
    assert client.post(BASE, headers=headers, json=values("位置", is_reference=True, topic_id="la.vectors")).status_code == 422
    admin_topic = client.get(BASE, headers=headers).json()["groups"][0]["topics"][0]
    student_topic = client.get("/api/v1/courses/physics/outline").json()["groups"][0]["topics"][0]
    assert not {"is_reference", "owner_title"} & admin_topic.keys()
    assert not {"is_reference", "owner_course"} & student_topic.keys()
