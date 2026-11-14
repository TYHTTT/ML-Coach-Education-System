import json

import psycopg
import pytest

from app.services.topic_management import TopicManagement
from tests.test_course_management import api, protected_api, COURSE  # noqa: F401
from tests.test_topic_management import BASE, create, values
from tests.test_permanent_topic_deletion import history, snapshot


def remove(client, headers, stage, topics, title="力学"):
    return client.request("DELETE", BASE + f"/groups/{stage}", headers=headers, json={"title": title, "topic_ids": topics})


@pytest.mark.parametrize("token", [None, "student-session", "expired-admin-session"])
def test_chapter_delete_requires_admin(protected_api, token):
    response = remove(protected_api, {"Authorization": f"Bearer {token}"} if token else {}, 1, ["physics.test"])
    assert response.status_code == 401


@pytest.mark.parametrize("payload", [{}, {"title": "力学", "topic_ids": ["physics.test", "physics.test"]},
    {"title": " ", "topic_ids": ["physics.test"]}, {"title": "力学", "topic_ids": ["unsafe"]}])
def test_chapter_delete_requires_a_valid_reviewed_member_list(protected_api, payload):
    assert protected_api.request("DELETE", BASE + "/groups/1", headers={"Authorization": "Bearer admin-session"}, json=payload).status_code == 422


@pytest.mark.parametrize("stage", [0, 1000, "invalid"])
def test_chapter_delete_validates_stage(protected_api, stage):
    assert remove(protected_api, {"Authorization": "Bearer admin-session"}, stage, ["physics.test"]).status_code == 422


def test_chapter_deletes_all_members_and_data_including_legacy_and_cross_course_edges(api):
    client, app, headers, student_headers, student = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    a = create(client, headers, "删除一", stage=2, stage_title="待删章", related_topic_ids=["la.vectors"])
    b = create(client, headers, "删除二", stage=2, stage_title="待删章", related_topic_ids=[a])
    legacy = create(client, headers, "历史知识点", stage=2, stage_title="待删章", related_topic_ids=["prob.basics"])
    keep = create(client, headers, "保留", related_topic_ids=[a, "la.vectors"])
    later = create(client, headers, "后续", stage=3, stage_title="后续章")
    targets = [a, b, legacy]
    with app.state.learning_repository._connect() as connection:
        for index, topic in enumerate(targets): history(connection, student["id"], topic, f"drop-{index}")
        history(connection, student["id"], keep, "keep")
        history(connection, student["id"], later, "later")
        connection.execute("UPDATE curriculum_topics SET active=0 WHERE id=?", (legacy,))
        before = snapshot(connection)
    result = remove(client, headers, 2, targets, "待删章")
    assert result.status_code == 200, result.text
    assert [group["id"] for group in result.json()["groups"]] == ["stage-1", "stage-3"]
    assert result.json()["removed_topics"] == []
    assert remove(client, headers, 2, targets, "待删章").status_code == 404
    with app.state.learning_repository._connect() as connection:
        after = snapshot(connection)
    for table in before:
        if table == "courses":
            assert [{k: v for k, v in row["data"].items() if k != "updated_at"} for row in before[table]] == [{k: v for k, v in row["data"].items() if k != "updated_at"} for row in after[table]]
        elif table == "course_chapters":
            assert after[table] == [row for row in before[table] if not (row["data"]["course_id"] == "physics" and row["data"]["stage"] == 2)]
        else:
            expected = [row for row in before[table] if not any(topic in json.dumps(row["data"]) for topic in targets) and not any(str(value).startswith("drop-") for value in row["data"].values())]
            assert after[table] == expected, table
    outline = client.get("/api/v1/courses/physics/outline", headers=student_headers).json()
    assert [g["id"] for g in outline["groups"]] == ["stage-1", "stage-3"]
    for prefix, auth in (("", student_headers), ("admin/", headers)):
        graph = client.get("/api/v1/" + prefix + "knowledge-graph", headers=auth).json()
        assert not set(targets) & {node["id"] for node in graph["nodes"]}
        assert len(graph["edges"]) == 1
    ordered = client.post(BASE + "/groups/order", headers=headers, json={"group_ids": ["stage-3", "stage-1"]})
    assert ordered.status_code == 200
    assert ordered.json()["groups"][0]["topics"][0]["id"] == later
    assert create(client, headers, "新章节知识点", stage=3, stage_title="新章节")


@pytest.mark.parametrize("change", ["add", "move", "rename", "reorder", "foreign_member"])
def test_stale_or_foreign_chapter_confirmation_cannot_delete_unreviewed_data(api, change):
    client, app, headers, _, _ = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    a = create(client, headers, "位置")
    b = create(client, headers, "能量", stage=2, stage_title="能量章")
    reviewed = [a]
    if change == "add": create(client, headers, "新增成员")
    elif change == "move": assert client.put(BASE + "/" + b, headers=headers, json=values("能量")).status_code == 200
    elif change == "rename": assert client.patch(BASE + "/groups/1", headers=headers, json={"title": "改名章"}).status_code == 200
    elif change == "reorder": assert client.post(BASE + "/groups/order", headers=headers, json={"group_ids": ["stage-2", "stage-1"]}).status_code == 200
    else: reviewed = ["la.vectors"]
    with app.state.learning_repository._connect() as connection: before = snapshot(connection)
    assert remove(client, headers, 1, reviewed).status_code == 409
    with app.state.learning_repository._connect() as connection: assert snapshot(connection) == before


def test_failure_of_one_member_rolls_back_the_entire_chapter(api):
    client, app, headers, _, student = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    members = [create(client, headers, title, related_topic_ids=["la.vectors"]) for title in ("一", "二")]
    with app.state.learning_repository._connect() as connection:
        for index, topic in enumerate(members): history(connection, student["id"], topic, f"drop-{index}")
        connection.execute("CREATE TABLE chapter_delete_guard(topic_id TEXT REFERENCES curriculum_topics(id))")
        connection.execute("INSERT INTO chapter_delete_guard VALUES (?)", (members[-1],))
        before = snapshot(connection)
    try:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            TopicManagement(app.state.settings.database_url).remove_stage("physics", 1, "力学", members)
        with app.state.learning_repository._connect() as connection: assert snapshot(connection) == before
    finally:
        with app.state.learning_repository._connect() as connection: connection.execute("DROP TABLE chapter_delete_guard")


def test_last_chapter_with_only_legacy_members_can_be_deleted_in_disabled_course(api):
    client, app, headers, _, _ = api
    client.post("/api/v1/admin/courses", headers=headers, json={**COURSE, "active": False})
    a = create(client, headers, "历史知识点")
    with app.state.learning_repository._connect() as connection:
        connection.execute("UPDATE curriculum_topics SET active=0 WHERE id=?", (a,))
    outline = client.get(BASE, headers=headers).json()
    assert outline["groups"][0]["topics"] == [] and len(outline["removed_topics"]) == 1
    result = remove(client, headers, 1, [a])
    assert result.status_code == 200
    assert result.json()["groups"] == result.json()["removed_topics"] == []
    assert client.get("/api/v1/admin/courses/physics", headers=headers).status_code == 200
    assert remove(client, headers, 99, [a]).status_code == 404
    client.delete("/api/v1/admin/courses/physics", headers=headers)
    assert remove(client, headers, 1, [a]).status_code == 404
