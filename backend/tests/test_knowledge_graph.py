import pytest

from tests.test_course_management import api, protected_api, COURSE  # noqa: F401
from tests.test_topic_management import BASE, create


@pytest.mark.parametrize("token", [None, "student-session", "expired-admin-session"])
def test_admin_graph_requires_administrator(protected_api, token):
    response = protected_api.get("/api/v1/admin/knowledge-graph", headers={"Authorization": f"Bearer {token}"} if token else {})
    assert response.status_code == 401


def test_graph_authentication_and_owning_course_clusters(api):
    client, app, admin, student, _ = api
    assert client.get("/api/v1/knowledge-graph").status_code == 422
    for token in ("expired-student", admin["Authorization"].split(" ")[1]):
        assert client.get("/api/v1/knowledge-graph", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert client.get("/api/v1/admin/knowledge-graph", headers=student).status_code == 401
    client.post("/api/v1/admin/courses", headers=admin, json=COURSE)
    a = create(client, admin, "位置", related_topic_ids=["la.vectors"])
    b = create(client, admin, "速度", related_topic_ids=[a])
    graph = client.get("/api/v1/knowledge-graph", headers=student)
    assert graph.status_code == 200
    data = graph.json()
    assert set(data) == {"courses", "nodes", "edges"}
    assert {n["id"] for n in data["nodes"] if n["course"] == "physics"} == {a, b}
    assert len({n["id"] for n in data["nodes"]}) == len(data["nodes"])
    assert len(data["edges"]) == 2
    assert {tuple(sorted((e["source"], e["target"]))) for e in data["edges"]} == {tuple(sorted((a, "la.vectors"))), tuple(sorted((a, b)))}
    assert all(e["type"] == "related" for e in data["edges"])
    assert all(set(n) == {"id", "course", "title", "description", "stage", "stage_title", "order_index"} for n in data["nodes"])
    assert data == client.get("/api/v1/admin/knowledge-graph", headers=admin).json()
    with app.state.learning_repository._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM topic_relations").fetchone()["n"] == 2


def test_graph_excludes_hidden_courses_and_permanently_deleted_endpoints(api):
    client, _, admin, student, _ = api
    client.post("/api/v1/admin/courses", headers=admin, json=COURSE)
    a = create(client, admin, "位置", related_topic_ids=["la.vectors"])
    b = create(client, admin, "速度", related_topic_ids=[a])
    def graph(role):
        return client.get("/api/v1/" + ("admin/" if role is admin else "") + "knowledge-graph", headers=role).json()
    client.patch("/api/v1/admin/courses/physics", headers=admin, json={"active": False})
    assert not any(c["id"] == "physics" for c in graph(student)["courses"])
    assert graph(student)["edges"] == []
    assert next(c for c in graph(admin)["courses"] if c["id"] == "physics")["active"] is False
    assert len(graph(admin)["edges"]) == 2
    client.delete(BASE + "/" + b, headers=admin)
    assert b not in {n["id"] for n in graph(admin)["nodes"]}
    assert len(graph(admin)["edges"]) == 1
    assert client.post(BASE + "/" + b + "/restore", headers=admin).status_code == 404
    client.patch("/api/v1/admin/courses/physics", headers=admin, json={"active": True})
    assert len(graph(student)["edges"]) == 1
    client.delete("/api/v1/admin/courses/physics", headers=admin)
    for role in (student, admin):
        data = graph(role)
        assert not any(c["id"] == "physics" for c in data["courses"])
        assert data["edges"] == []
        assert all(n["course"] != "physics" for n in data["nodes"])


def test_graph_keeps_empty_courses_and_isolated_nodes_without_inventing_edges(api):
    client, app, admin, student, _ = api
    client.post("/api/v1/admin/courses", headers=admin, json=COURSE)
    empty = client.get("/api/v1/knowledge-graph", headers=student).json()
    assert any(c["id"] == "physics" for c in empty["courses"])
    assert not any(n["course"] == "physics" for n in empty["nodes"])
    assert empty["edges"] == []
    a = create(client, admin, "位置")
    assert a in {n["id"] for n in client.get("/api/v1/knowledge-graph", headers=student).json()["nodes"]}
    with app.state.learning_repository._connect() as connection:
        connection.execute("UPDATE curriculum_topics SET active=0")
    data = client.get("/api/v1/knowledge-graph", headers=student).json()
    assert data["courses"] and data["nodes"] == [] and data["edges"] == []
