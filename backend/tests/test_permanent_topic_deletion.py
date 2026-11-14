import json

from fastapi.testclient import TestClient
import psycopg
import pytest

from app.main import create_app
from app.services.topic_management import TopicManagement
from tests.mocks import MockLLMClient
from tests.test_course_management import api, COURSE  # noqa: F401
from tests.test_topic_management import BASE, create


def history(connection, student_id, topic_id, prefix):
    now = "2026-11-14T00:00:00+00:00"
    connection.execute("INSERT INTO student_topic_states(student_id,topic_id,status,updated_at) VALUES (?,?,'learning',?)", (student_id, topic_id, now))
    connection.execute("INSERT INTO student_dimension_states(student_id,topic_id,dimension,updated_at) VALUES (?,?,'concept',?)", (student_id, topic_id, now))
    connection.execute("""INSERT INTO practice_sets(id,student_id,topic_id,course,mode,status,requested_difficulty,source_snapshot_json,created_at)
        VALUES (?,?,?,'physics','practice','submitted','easy','[]',?)""", (prefix + "-set", student_id, topic_id, now))
    connection.execute("""INSERT INTO practice_questions(id,practice_set_id,position,question_type,difficulty,question,dimensions_json,
        answer_key_json,rubric_json,source_ids_json,question_hash,created_at,topic_ids_json)
        VALUES (?,?,1,'short_answer','easy','测试题目','[]','{}','{}','[]',?,?,?)""",
        (prefix + "-question", prefix + "-set", prefix + "-hash", now, json.dumps([topic_id])))
    connection.execute("""INSERT INTO practice_submissions(id,practice_set_id,student_id,client_submission_id,total_score,evaluation_status,gate_result_json,created_at)
        VALUES (?,?,?,?,80,'evaluated','{}',?)""", (prefix + "-submission", prefix + "-set", student_id, prefix + "-client", now))
    connection.execute("""INSERT INTO practice_attempts(id,submission_id,question_id,student_id,answer_text,score,verdict,dimension_scores_json,
        correct_points_json,missing_points_json,misconception_tags_json,feedback,reference_answer,evidence_source_ids_json,evaluator_confidence,evaluation_reliable,created_at)
        VALUES (?,?,?,?,'测试答案',80,'correct','{}','[]','[]','[]','反馈','答案','[]',0.9,1,?)""",
        (prefix + "-attempt", prefix + "-submission", prefix + "-question", student_id, now))
    connection.execute("""INSERT INTO misconception_events(id,student_id,topic_id,attempt_id,tag,evidence,created_at)
        VALUES (?,?,?,?,'concept','测试证据',?)""", (prefix + "-event", student_id, topic_id, prefix + "-attempt", now))
    connection.execute("""INSERT INTO learning_sessions(id,student_id,course,topic_id,state,started_at,created_at,updated_at)
        VALUES (?,?,'physics',?,'learning',?,?,?)""", (prefix + "-session", student_id, topic_id, now, now, now))


TABLES = ("curriculum_topics", "topic_placements", "topic_relations", "student_topic_states", "student_dimension_states",
          "practice_sets", "practice_questions", "practice_submissions", "practice_attempts", "misconception_events", "learning_sessions", "courses")


def snapshot(connection):
    return {table: connection.execute(f"SELECT to_jsonb(t) AS data FROM {table} t ORDER BY to_jsonb(t)::text").fetchall() for table in TABLES}


def test_permanent_delete_cleans_all_history_and_cross_course_edges_without_touching_other_topics(api):
    client, app, headers, student_headers, student = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    target = create(client, headers, "待删除", related_topic_ids=["la.vectors", "prob.basics"])
    keep = create(client, headers, "保留", related_topic_ids=["la.vectors", target])
    with app.state.learning_repository._connect() as connection:
        history(connection, student["id"], target, "delete")
        history(connection, student["id"], keep, "keep")
        before = snapshot(connection)
        assert connection.execute("SELECT count(*) AS n FROM topic_relations WHERE topic_a_id=?", (target,)).fetchone()["n"] > 0
        assert connection.execute("SELECT count(*) AS n FROM topic_relations WHERE topic_b_id=?", (target,)).fetchone()["n"] > 0
    response = client.delete(BASE + "/" + target, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["removed_topics"] == []
    with app.state.learning_repository._connect() as connection:
        after = snapshot(connection)
        for table in TABLES:
            if table == "courses":
                for old, new in zip(before[table], after[table]):
                    assert {k: v for k, v in old["data"].items() if k != "updated_at"} == {k: v for k, v in new["data"].items() if k != "updated_at"}
                continue
            expected = [row for row in before[table] if target not in json.dumps(row["data"]) and not any(str(value).startswith("delete-") for value in row["data"].values())]
            assert after[table] == expected, table
        assert connection.execute("SELECT count(*) AS n FROM topic_relations").fetchone()["n"] == 1
        assert connection.execute("SELECT count(*) AS n FROM learning_sessions WHERE topic_id IS NULL").fetchone()["n"] == 0
        assert connection.execute("SELECT 1 FROM students WHERE id=?", (student["id"],)).fetchone()
    for prefix, auth in (("", student_headers), ("admin/", headers)):
        graph = client.get("/api/v1/" + prefix + "knowledge-graph", headers=auth).json()
        assert target not in {node["id"] for node in graph["nodes"]}
        assert len(graph["edges"]) == 1
    assert client.delete(BASE + "/" + target, headers=headers).status_code == 404
    assert client.post(BASE + "/" + target + "/restore", headers=headers).status_code == 404
    assert client.get("/api/v1/curriculum/topics/" + target, headers=student_headers).status_code == 404


def test_failed_delete_rolls_back_every_related_table(api):
    client, app, headers, _, student = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    target = create(client, headers, "原子删除", related_topic_ids=["la.vectors"])
    with app.state.learning_repository._connect() as connection:
        history(connection, student["id"], target, "delete")
        connection.execute("CREATE TABLE deletion_guard(topic_id TEXT REFERENCES curriculum_topics(id))")
        connection.execute("INSERT INTO deletion_guard VALUES (?)", (target,))
        before = snapshot(connection)
    try:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            TopicManagement(app.state.settings.database_url).remove("physics", target)
        with app.state.learning_repository._connect() as connection:
            assert snapshot(connection) == before
    finally:
        with app.state.learning_repository._connect() as connection:
            connection.execute("DROP TABLE deletion_guard")


def test_legacy_inactive_topic_can_be_permanently_cleaned_up(api):
    client, app, headers, _, student = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    target = create(client, headers, "历史软删除", related_topic_ids=["la.vectors"])
    with app.state.learning_repository._connect() as connection:
        history(connection, student["id"], target, "legacy")
        connection.execute("UPDATE curriculum_topics SET active=0 WHERE id=?", (target,))
    assert client.get(BASE, headers=headers).json()["removed_topics"][0]["id"] == target
    assert client.delete(BASE + "/" + target, headers=headers).json()["removed_topics"] == []
    with app.state.learning_repository._connect() as connection:
        assert not connection.execute("SELECT id FROM curriculum_topics WHERE id=?", (target,)).fetchone()
        assert not connection.execute("SELECT id FROM practice_sets WHERE topic_id=?", (target,)).fetchone()


def test_restart_does_not_recreate_an_intentionally_empty_curriculum(api):
    client, app, headers, _, _ = api
    client.post("/api/v1/admin/courses", headers=headers, json=COURSE)
    target = create(client, headers, "最后一个知识点")
    with app.state.learning_repository._connect() as connection:
        connection.execute("DELETE FROM topic_placements WHERE topic_id<>?", (target,))
        connection.execute("DELETE FROM curriculum_topics WHERE id<>?", (target,))
    assert client.delete(BASE + "/" + target, headers=headers).status_code == 200
    restarted_app = create_app(app.state.settings, llm_client=MockLLMClient())
    with TestClient(restarted_app) as restarted:
        assert restarted.get(BASE, headers=headers).json()["groups"] == []
        with app.state.learning_repository._connect() as connection:
            assert connection.execute("SELECT count(*) AS n FROM curriculum_topics").fetchone()["n"] == 0
