from __future__ import annotations

import json

import pytest

from app.core.types import Course
from app.curriculum.models import CurriculumSeed
from app.curriculum.seed import CurriculumSeedError, seed_curriculum
from app.curriculum.validation import (
    CurriculumCycleError,
    CrossCourseDependencyError,
    validate_curriculum,
)
from app.services.learning_repository import LearningRepository


def _topic(
    topic_id: str,
    order: int,
    prerequisites: list[str] | None = None,
) -> dict:
    return {
        "id": topic_id,
        "slug": topic_id.split(".", 1)[1],
        "title": topic_id,
        "stage": 1,
        "stage_title": "测试阶段",
        "order_index": order,
        "description": "测试知识点",
        "learning_objectives": ["完成测试目标"],
        "aliases": [],
        "retrieval_keywords": [topic_id],
        "difficulty": "easy",
        "required_dimensions": ["concept"],
        "active": True,
        "prerequisites": [
            {"topic_id": dependency, "required_mastery": 0.8}
            for dependency in prerequisites or []
        ],
    }


@pytest.fixture
def repository(postgres_test_database_url) -> LearningRepository:
    value = LearningRepository(postgres_test_database_url)
    return value


def test_default_seed_is_complete_and_idempotent(repository: LearningRepository) -> None:
    first = seed_curriculum(repository)
    second = seed_curriculum(repository)

    assert first == second == {
        Course.MACHINE_LEARNING.value: 30,
        Course.ADVANCED_MATHEMATICS.value: 23,
        Course.LINEAR_ALGEBRA.value: 10,
        Course.PROBABILITY_STATISTICS.value: 11,
    }
    assert len(repository.list_topics(Course.MACHINE_LEARNING)) == 30
    assert len(repository.list_topics(Course.ADVANCED_MATHEMATICS)) == 23
    with repository._connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM curriculum_topics"
        ).fetchone()["count"] == 74
        ids = connection.execute(
            "SELECT id FROM curriculum_topics GROUP BY id HAVING COUNT(*) > 1"
        ).fetchall()
        assert ids == []


def test_cycle_reports_concrete_path() -> None:
    seed = CurriculumSeed.model_validate(
        {
            "course": "machine_learning",
            "topics": [
                _topic("ml.a", 1, ["ml.b"]),
                _topic("ml.b", 2, ["ml.c"]),
                _topic("ml.c", 3, ["ml.a"]),
            ],
        }
    )

    with pytest.raises(CurriculumCycleError) as caught:
        validate_curriculum([seed])

    assert caught.value.cycle[0] == caught.value.cycle[-1]
    assert set(caught.value.cycle[:-1]) == {"ml.a", "ml.b", "ml.c"}
    assert " -> " in str(caught.value)


def test_cross_course_prerequisite_is_allowed(repository: LearningRepository) -> None:
    ml_seed = CurriculumSeed.model_validate(
        {
            "course": "machine_learning",
            "topics": [_topic("ml.a", 1, ["math.a"])],
        }
    )
    math_seed = CurriculumSeed.model_validate(
        {
            "course": "advanced_mathematics",
            "topics": [_topic("math.a", 1)],
        }
    )

    validate_curriculum([ml_seed, math_seed])
    repository.upsert_curriculum([ml_seed, math_seed])
    assert repository.list_prerequisites("ml.a")[0]["id"] == "math.a"


def test_seed_failure_does_not_partially_replace_database(
    repository: LearningRepository, tmp_path
) -> None:
    seed_curriculum(repository)
    invalid = {
        "course": "machine_learning",
        "topics": [
            _topic("ml.a", 1, ["ml.b"]),
            _topic("ml.b", 2, ["ml.a"]),
        ],
    }
    path = tmp_path / "cycle.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")

    with pytest.raises(CurriculumSeedError, match="循环依赖"):
        seed_curriculum(repository, [path])

    assert len(repository.list_topics(Course.MACHINE_LEARNING)) == 30


def test_topics_are_isolated_by_course(repository: LearningRepository) -> None:
    seed_curriculum(repository)
    ml_ids = {item["id"] for item in repository.list_topics(Course.MACHINE_LEARNING)}
    math_ids = {
        item["id"] for item in repository.list_topics(Course.ADVANCED_MATHEMATICS)
    }

    assert ml_ids
    assert math_ids
    assert ml_ids.isdisjoint(math_ids)
    assert all(topic_id.startswith("ml.") for topic_id in ml_ids)
    assert all(topic_id.startswith("math.") for topic_id in math_ids)
