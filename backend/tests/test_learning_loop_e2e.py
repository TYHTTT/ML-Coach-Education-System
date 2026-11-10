from __future__ import annotations

import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class QueueLLM:
    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.calls: list[list[dict[str, str]]] = []

    async def generate(self, messages, temperature=None):
        self.calls.append(messages)
        if not self.answers:
            raise AssertionError("unexpected LLM call")
        return self.answers.pop(0)


    async def run(self, messages, **kwargs):
        course = kwargs["course"].value
        return {"answer": "Dify 课程资料", "resources": [{
            "content": "课程定义、计算、机制、应用与边界；六组七个样本共有 42 个。",
            "document_id": "dify-test-" + course, "document_name": "Dify 测试课程原文",
            "doc_metadata": {"course": course, "topic_id": kwargs.get("topic_id")},
        }]}


def _numeric_question(question_id: str, position: int, dimension: str) -> dict:
    return {
        "question_id": question_id,
        "question_type": "numeric",
        "difficulty": "medium",
        "question": f"请根据给定条件计算第 {position} 个结果：6 组数据，每组 7 个样本，一共有多少个样本？",
        "dimensions": {dimension: 1.0},
        "options": None,
        "answer_key": {
            "canonical_answer": "42",
            "key_points": [],
            "accepted_variants": [],
            "numeric_answer": 42,
            "tolerance": 0,
            "correct_option": None,
        },
        "rubric": [{"criterion": "数值与资料支持的结果一致", "points": 100}],
        "source_ids": ["S1"],
        "position": position,
        "max_score": 100,
    }


def _open_question(
    question_id: str,
    position: int,
    dimension: str,
    question_type: str,
) -> dict:
    return {
        "question_id": question_id,
        "question_type": question_type,
        "difficulty": "hard",
        "question": "请综合课程资料说明该知识点在实际问题中的应用边界。",
        "dimensions": {dimension: 1.0},
        "options": None,
        "answer_key": {
            "canonical_answer": "应说明定义、适用条件与应用边界。",
            "key_points": ["定义", "条件", "应用边界"],
            "accepted_variants": [],
            "numeric_answer": None,
            "tolerance": None,
            "correct_option": None,
        },
        "rubric": [{"criterion": "完整说明定义、条件和边界", "points": 100}],
        "source_ids": ["S1"],
        "position": position,
        "max_score": 100,
    }


def _generated_set(
    dimensions: list[str],
    *,
    checkpoint: bool,
    open_question_type: str,
) -> str:
    questions = [
        _numeric_question(f"q-{index}", index, dimension)
        for index, dimension in enumerate(dimensions, 1)
    ]
    if checkpoint:
        for question in questions:
            question["question"] = "综合验收：" + str(question["question"])
        questions[-1] = _open_question(
            "q-3",
            3,
            dimensions[-1],
            open_question_type,
        )
    return json.dumps({"questions": questions}, ensure_ascii=False)


def _perfect_evaluation(dimension: str) -> str:
    return json.dumps(
        {
            "score": 100,
            "verdict": "correct",
            "dimension_scores": {dimension: 100},
            "correct_points": ["完整覆盖评分点"],
            "missing_points": [],
            "misconception_tags": [],
            "critical_misconception": False,
            "feedback": "回答完整且有课程资料支持。",
            "reference_answer": "应说明定义、适用条件与应用边界。",
            "evidence_source_ids": ["S1"],
            "evaluator_confidence": 0.99,
            "evaluation_reliable": True,
        },
        ensure_ascii=False,
    )


def _submit_all(
    client: TestClient,
    student_id: str,
    practice_set: dict,
) -> tuple[dict, dict]:
    submission = {
        "client_submission_id": str(uuid4()),
        "answers": [
            {
                "question_id": question["question_id"],
                "answer": (
                    "42"
                    if question["question_type"] == "numeric"
                    else "我说明了定义、适用条件和应用边界。"
                ),
            }
            for question in practice_set["questions"]
        ],
    }
    response = client.post(
        f"/api/v1/practice/sets/{practice_set['practice_set_id']}/submit",
        headers={"X-Student-ID": student_id},
        json=submission,
    )
    assert response.status_code == 200, response.text
    return response.json(), submission


def _complete_first_topic(
    client: TestClient,
    llm: QueueLLM,
    *,
    student_id: str,
    course: str,
    topic_id: str,
) -> None:
    headers = {"X-Student-ID": student_id}
    started = client.post(f"/api/v1/learning/topics/{topic_id}/start", headers=headers)
    assert started.status_code == 200, started.text
    assert started.json()["mastery"] is None

    practice_response = client.post(
        "/api/v1/practice/sets",
        headers=headers,
        json={
            "topic_id": topic_id,
            "mode": "practice",
            "count": 3,
            "difficulty": "medium",
        },
    )
    assert practice_response.status_code == 201, practice_response.text
    practice = practice_response.json()
    serialized = practice_response.text
    for forbidden in (
        "answer_key",
        "rubric",
        "canonical_answer",
        "numeric_answer",
        "correct_option",
        "source_snapshot",
    ):
        assert forbidden not in serialized
    assert len(practice["questions"]) == 3
    assert practice["source_summary"]

    calls_before_submit = len(llm.calls)
    practice_result, submission = _submit_all(client, student_id, practice)
    assert len(llm.calls) == calls_before_submit
    assert practice_result["total_score"] == 100
    assert practice_result["mastery_before"] == 0.5
    assert practice_result["mastery_after"] == 0.8
    assert practice_result["next_action"] == "take_checkpoint"

    replay = client.post(
        f"/api/v1/practice/sets/{practice['practice_set_id']}/submit",
        headers=headers,
        json=submission,
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert len(llm.calls) == calls_before_submit

    checkpoint_response = client.post(
        "/api/v1/practice/sets",
        headers=headers,
        json={
            "topic_id": topic_id,
            "mode": "checkpoint",
            "count": 3,
            "difficulty": "hard",
        },
    )
    assert checkpoint_response.status_code == 201, checkpoint_response.text
    checkpoint = checkpoint_response.json()
    assert len(llm.calls) == calls_before_submit + 1  # Dynamic generation uses Dify evidence.
    assert len(
        {
            dimension
            for question in checkpoint["questions"]
            for dimension in question["dimensions"]
        }
    ) >= 3
    assert not all(
        question["question_type"] == "multiple_choice"
        for question in checkpoint["questions"]
    )

    internal = client.app.state.learning_repository.get_practice_set_internal(checkpoint["practice_set_id"], student_id=student_id)
    open_question = next(question for question in internal.questions if question.question_type != "numeric")
    evaluation = json.loads(llm.answers[0])
    evaluation["evidence_source_ids"] = open_question.source_ids
    llm.answers[0] = json.dumps(evaluation, ensure_ascii=False)
    checkpoint_result, _ = _submit_all(client, student_id, checkpoint)
    assert len(llm.calls) == calls_before_submit + 2  # Plus the open-answer evaluator.
    assert checkpoint_result["total_score"] == 100
    assert checkpoint_result["gate"]["passed"] is True
    assert checkpoint_result["next_action"] == "continue_to_next_topic"

    detail = client.get(
        f"/api/v1/curriculum/topics/{topic_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "mastered"
    assert detail.json()["course"] == course


def test_complete_learning_loop_for_both_courses_and_persist_after_restart(
    tmp_path, postgres_test_database_url,
) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=postgres_test_database_url,
    )
    ml_dimensions = ["concept", "mechanism", "application"]
    math_dimensions = ["concept", "calculation", "application"]
    llm = QueueLLM(
        [
            _generated_set(
                ml_dimensions,
                checkpoint=False,
                open_question_type="case_analysis",
            ),
            _generated_set(ml_dimensions, checkpoint=True, open_question_type="case_analysis"),
            _perfect_evaluation("application"),
            _generated_set(
                math_dimensions,
                checkpoint=False,
                open_question_type="application",
            ),
            _generated_set(math_dimensions, checkpoint=True, open_question_type="application"),
            _perfect_evaluation("application"),
        ]
    )
    application = create_app(
        settings,
        llm_client=llm,
    )
    with TestClient(application) as client:
        student = client.post("/api/v1/students/anonymous")
        assert student.status_code == 201
        student_id = student.json()["student_id"]

        locked = client.post(
            "/api/v1/learning/topics/ml.logistic_regression/start",
            headers={"X-Student-ID": student_id},
        )
        assert locked.status_code == 200
        assert locked.json()["status"] == "learning"
        assert locked.json()["locked_reason"]

        _complete_first_topic(
            client,
            llm,
            student_id=student_id,
            course="machine_learning",
            topic_id="ml.machine_learning_basics",
        )
        _complete_first_topic(
            client,
            llm,
            student_id=student_id,
            course="advanced_mathematics",
            topic_id="math.functions",
        )
        assert llm.answers == []

    # A fresh FastAPI process over the same PostgreSQL database sees the same
    # anonymous learner state; startup seed remains idempotent.
    restarted = create_app(
        settings,
        llm_client=QueueLLM([]),
    )
    with TestClient(restarted) as client:
        for course, first_topic in (
            ("machine_learning", "ml.machine_learning_basics"),
            ("advanced_mathematics", "math.functions"),
        ):
            curriculum = client.get(
                "/api/v1/curriculum/topics",
                params={"course": course},
                headers={"X-Student-ID": student_id},
            )
            assert curriculum.status_code == 200
            topics = [
                topic
                for stage in curriculum.json()["stages"]
                for topic in stage["topics"]
            ]
            assert next(item for item in topics if item["id"] == first_topic)[
                "status"
            ] == "mastered"
