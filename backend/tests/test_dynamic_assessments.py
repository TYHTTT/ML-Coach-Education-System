"""Default course-material generation, without network or production data."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import learning_grounding_from_request
from app.api.content import prerequisite_generator
from app.content.seeds.core import build_content
from app.main import create_app
from app.services.content_repository import ContentRepository
from app.services.learning_grounding import GroundingResult
from app.services.practice_service import PracticeService
from tests.test_learning_loop_e2e import QueueLLM, _numeric_question


SOURCE = {
    "source_id": "S1", "document_id": "mock-course-document",
    "source_file": "mock-course.md", "title": "测试课程资料",
    "chunk_index": 0, "content": "测试用真实检索边界夹具：向量内积逐项相乘求和，六组七个样本共42个。",
}


class RecordingGrounding:
    def __init__(self):
        self.calls = []
        self.sources = [SOURCE]

    async def retrieve(self, **kwargs):
        self.calls.append(kwargs)
        return GroundingResult(query="mock course query", source_snapshot=self.sources)


@pytest.fixture
def dynamic_app(settings):
    configured = settings.model_copy(update={
        "question_generation_max_retries": 0, "evaluation_max_repair_attempts": 0,
    })
    llm = QueueLLM([])
    grounding = RecordingGrounding()
    app = create_app(configured, llm_client=llm)
    app.dependency_overrides[learning_grounding_from_request] = lambda: grounding
    app.dependency_overrides[prerequisite_generator] = lambda: PracticeService(
        settings=configured, repository=app.state.learning_repository,
        grounding=grounding, llm_client=llm,
    )
    with TestClient(app) as client:
        account = app.state.learning_repository.register_student(username="dynamic_test", display_name="测试学生", password="test-password")
        sid = account["id"]; _tokens[sid] = account["access_token"]
        yield client, app.state.learning_repository, llm, grounding, sid


_tokens = {}


def headers(sid):
    return {"Authorization": "Bearer " + _tokens[sid]}


def generated(prefix, *, competency=None, checkpoint=False):
    dimensions = ["concept", "mechanism", "application"] if not competency else ["calculation"] * 3
    questions = []
    for position, dimension in enumerate(dimensions, 1):
        question = _numeric_question(str(position), position, dimension)
        question["question"] = prefix + "：" + question["question"]
        if competency:
            question["tested_competencies"] = [competency]
        questions.append(question)
    if checkpoint:
        questions[-1].update(question_type="multiple_choice", options=[
            {"option_id": "A", "text": "42"}, {"option_id": "B", "text": "36"},
        ])
        questions[-1]["answer_key"].update(correct_option="A", numeric_answer=None, tolerance=None, key_points=["六乘七等于42"])
    return json.dumps({"questions": questions}, ensure_ascii=False)


def assert_public(value):
    for hidden in ("answer_key", "rubric", "canonical_answer", "numeric_answer", "correct_option", "source_snapshot", "tested_competencies"):
        assert hidden not in json.dumps(value)
    assert SOURCE["content"] not in json.dumps(value, ensure_ascii=False)
    assert all("S1" not in q["question"] for q in value["questions"])


def submit(client, sid, value, *, prefix="/api/v1/practice/sets", answer="42", submission_id=None):
    return client.post(prefix + "/" + value["practice_set_id"] + "/submit", headers=headers(sid), json={
        "client_submission_id": submission_id or str(uuid4()),
        "answers": [{"question_id": q["question_id"], "answer": "A" if q["question_type"] == "multiple_choice" else answer}
                    for q in value["questions"]],
    })


def test_default_checkpoint_uses_dify_sources_and_saved_submission(dynamic_app):
    client, repo, llm, grounding, sid = dynamic_app
    topic = "ml.machine_learning_basics"
    llm.answers.extend([generated("主动练习"), generated("新的综合验收", checkpoint=True)])
    early = client.post("/api/v1/practice/sets", headers=headers(sid), json={"topic_id": topic, "mode": "checkpoint", "count": 3})
    assert early.status_code == 409 and not llm.calls
    practice = client.post("/api/v1/practice/sets", headers=headers(sid), json={"topic_id": topic, "mode": "practice", "count": 3})
    assert practice.status_code == 201, practice.text
    result = submit(client, sid, practice.json())
    assert result.status_code == 200 and result.json()["next_action"] == "take_checkpoint"
    # A prior unmet prerequisite can leave this status stale; current evidence
    # must be reevaluated instead of permanently locking the learner out.
    with repo._connect() as c:
        c.execute("UPDATE student_topic_states SET status='practicing' WHERE student_id=? AND topic_id=?", (sid, topic))
    response = client.post("/api/v1/practice/sets", headers=headers(sid), json={"topic_id": topic, "mode": "checkpoint", "count": 3})
    assert response.status_code == 201, response.text
    value = response.json()
    assert len(llm.calls) == 2 and len(grounding.calls) == 2
    assert grounding.calls[-1]["course"].value == "machine_learning"
    assert SOURCE["content"] in json.dumps(llm.calls[-1], ensure_ascii=False)
    assert_public(value)
    for route in ("/api/v1/practice/sets/", "/api/v1/assessments/"):
        read = client.get(route + value["practice_set_id"], headers=headers(sid))
        assert read.status_code == 200
        assert_public(read.json())
    replay_id = str(uuid4())
    result = submit(client, sid, value, submission_id=replay_id)
    assert result.status_code == 200 and result.json()["gate"]["passed"]
    replay = submit(client, sid, value, submission_id=replay_id)
    assert replay.json()["idempotent_replay"] and len(llm.calls) == 2


@pytest.mark.parametrize("mode", ["practice", "checkpoint"])
def test_default_generation_empty_sources_never_calls_llm_or_writes_questions(dynamic_app, mode):
    client, repo, llm, grounding, sid = dynamic_app
    topic = "ml.machine_learning_basics"
    if mode == "checkpoint":
        repo.ensure_topic_state(sid, topic)
        with repo._connect() as c:
            c.execute("UPDATE student_topic_states SET status='ready_for_checkpoint' WHERE student_id=?", (sid,))
    grounding.sources = []
    response = client.post("/api/v1/practice/sets", headers=headers(sid), json={"topic_id": topic, "mode": mode, "count": 3})
    assert response.json()["error"]["code"] == "KNOWLEDGE_INSUFFICIENT"
    assert not llm.calls
    with repo._connect() as c:
        assert c.execute("SELECT COUNT(*) FROM practice_sets").fetchone()["count"] == 0


def test_dynamic_prerequisite_uses_canonical_course_and_only_verifies_local_competency(dynamic_app):
    client, repo, llm, grounding, sid = dynamic_app
    topic = "ml.linear_regression"
    target = next(p for p in repo.get_unmet_prerequisites(sid, topic) if p["id"] == "la.dot_product")
    competency = target["required_competencies"][0]
    llm.answers.append(generated("内积局部验证", competency=competency))
    response = client.post("/api/v1/prerequisite-tests", headers=headers(sid), json={
        "topic_id": topic, "prerequisite_topic_id": "la.dot_product",
    })
    assert response.status_code == 201, response.text
    value = response.json()
    assert value["purpose"] == "prerequisite_test"
    assert value["topic_id"] == "la.dot_product"
    assert grounding.calls[0]["course"].value == "linear_algebra"
    assert grounding.calls[0]["topic_ids"] == ["la.dot_product"]
    assert competency in json.dumps(llm.calls[0], ensure_ascii=False)
    assert_public(value)
    internal = repo.get_practice_set_internal(value["id"], student_id=sid)
    assert internal.assessment_purpose == "prerequisite_test"
    assert internal.source_snapshot[0].document_id == SOURCE["document_id"]
    for suffix in ("hint", "solution"):
        assert client.post(f"/api/v1/assessments/{value['id']}/{suffix}", headers=headers(sid), json={
            "question_id": value["questions"][0]["question_id"], "attempt": "attempt",
        }).status_code == 404
    replay_id = str(uuid4())
    result = submit(client, sid, value, prefix="/api/v1/assessments", submission_id=replay_id)
    assert result.status_code == 200, result.text
    assert result.json()["total_score"] == 100
    assert result.json()["mastery_before"] == result.json()["mastery_after"] == 0.5
    assert "la.dot_product" not in {p["id"] for p in repo.get_unmet_prerequisites(sid, topic)}
    assert repo.get_topic_state(sid, "la.dot_product")["evidence_count"] == 0
    assert repo.get_topic_state(sid, "la.dot_product")["status"] != "mastered"
    replay = submit(client, sid, value, prefix="/api/v1/assessments", submission_id=replay_id)
    assert replay.json()["idempotent_replay"]
    with repo._connect() as c:
        assert c.execute("SELECT COUNT(*) FROM prerequisite_verifications WHERE student_id=?", (sid,)).fetchone()["count"] == 1
    assert len(llm.calls) == 1


@pytest.mark.parametrize("failure", ["no_sources", "wrong_competency", "source_id_leak"])
def test_dynamic_prerequisite_rejects_unsupported_or_invalid_generation_without_creating_a_test(dynamic_app, failure):
    client, repo, llm, grounding, sid = dynamic_app
    target = next(p for p in repo.get_unmet_prerequisites(sid, "ml.linear_regression") if p["id"] == "la.dot_product")
    competency = target["required_competencies"][0]
    if failure == "no_sources":
        grounding.sources = []
    else:
        llm.answers.append(generated("根据 S1 计算" if failure == "source_id_leak" else "局部验证", competency="invented.skill" if failure == "wrong_competency" else competency))
    response = client.post("/api/v1/prerequisite-tests", headers=headers(sid), json={"topic_id": "ml.linear_regression", "prerequisite_topic_id": "la.dot_product"})
    assert response.status_code != 201
    expected = "KNOWLEDGE_INSUFFICIENT" if failure == "no_sources" else "LLM_STRUCTURED_OUTPUT_INVALID"
    assert response.json()["error"]["code"] == expected
    with repo._connect() as c:
        assert c.execute("SELECT COUNT(*) FROM practice_sets").fetchone()["count"] == 0
        assert c.execute("SELECT COUNT(*) FROM prerequisite_verifications").fetchone()["count"] == 0


def test_dynamic_prerequisite_uncertain_retry_cannot_create_local_proof(dynamic_app):
    client, repo, llm, _, sid = dynamic_app
    target = next(p for p in repo.get_unmet_prerequisites(sid, "ml.linear_regression") if p["id"] == "la.dot_product")
    llm.answers.append(generated("独立局部验证", competency=target["required_competencies"][0]))
    response = client.post("/api/v1/prerequisite-tests", headers=headers(sid), json={"topic_id": "ml.linear_regression", "prerequisite_topic_id": "la.dot_product"})
    assert response.status_code == 201, response.text
    value = response.json()
    first = submit(client, sid, value, prefix="/api/v1/assessments", answer="NaN")
    assert first.status_code == 200 and first.json()["status"] == "evaluation_uncertain"
    second = submit(client, sid, value, prefix="/api/v1/assessments")
    assert second.status_code == 200 and second.json()["total_score"] == 100
    assert "la.dot_product" in {p["id"] for p in repo.get_unmet_prerequisites(sid, "ml.linear_regression")}
    with repo._connect() as c:
        assert c.execute("SELECT COUNT(*) FROM prerequisite_verifications").fetchone()["count"] == 0
