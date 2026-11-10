"""AI teaching examples use the course-scoped Dify Agent, never exam keys."""
from __future__ import annotations

import pytest

from app.core.types import Course
from app.prompts.learning import get_learning_prompt


@pytest.mark.parametrize("course", list(Course))
def test_example_and_teaching_prompts_require_concrete_grounded_steps(course):
    example = get_learning_prompt(course, "worked_example")
    teaching = get_learning_prompt(course, "topic_teaching")
    assert "默认提供两道" in example
    assert "逐步解答" in example and "验算" in example
    assert "基于课程资料原理编写的教学例题" in example
    assert "HyDE" in example and "不得编造" in example
    assert "不读取考试答案" in example
    assert "至少包含一道具体的完整分步例题" in teaching
    if course in {Course.LINEAR_ALGEBRA, Course.PROBABILITY_STATISTICS}:
        assert course.display_name in example


def test_example_request_requires_canonical_topic_and_matching_course(client, mock_llm):
    missing = client.post("/api/v1/chat", json={
        "course": "machine_learning", "message": "给我两道例题", "learning_mode": "worked_example",
    })
    assert missing.status_code == 422
    mismatch = client.post("/api/v1/chat", json={
        "course": "advanced_mathematics", "topic_id": "ml.machine_learning_basics",
        "message": "给我两道例题", "learning_mode": "worked_example",
    })
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "COURSE_TOPIC_MISMATCH"
    assert not mock_llm.calls


def test_dynamic_examples_use_dify_and_do_not_change_mastery(client, mock_llm):
    mock_llm.resources = [{"content": "监督学习使用带标签样本，分类预测类别，回归预测连续值。", "document_id": "dify-doc", "document_name": "课程原文"}]
    repository = client.app.state.learning_repository
    with repository._connect() as connection:
        before = {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                  for name in ("student_topic_states", "practice_sets", "practice_attempts", "worked_examples")}
    response = client.post("/api/v1/chat", json={
        "course": "machine_learning", "topic_id": "ml.machine_learning_basics",
        "message": "给两道分类和回归的分步例题。", "learning_mode": "worked_example",
    })
    assert response.status_code == 200, response.text
    assert response.json()["sources"][0]["source_file"] == "课程原文"
    assert len(mock_llm.calls) == 1
    assert "课程分步例题 Tutor" in mock_llm.calls[0][0]["content"]
    with repository._connect() as connection:
        after = {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in before}
    assert after == before
