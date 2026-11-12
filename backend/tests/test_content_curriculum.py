from __future__ import annotations

import pytest
import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.course_content import router
from app.core.config import Settings
from app.core.types import Course
from app.curriculum.seed import seed_curriculum
from app.services.learning_repository import LearningRepository
from app.services.topic_management import TopicManagement


@pytest.fixture
def repository(postgres_test_database_url):
    repo = LearningRepository(postgres_test_database_url)
    seed_curriculum(repo)
    return repo




def test_database_guards_registered_course(repository):
    with pytest.raises(psycopg.DatabaseError, match="unregistered_course"):
        with repository._connect() as connection:
            connection.execute("UPDATE curriculum_topics SET course='unregistered' WHERE id='la.vectors'")






def test_canonical_outline_shares_state_without_local_content_requirements(repository):
    account = repository.register_student(username="outline_test", display_name="测试学生", password="test-password")
    student = account["id"]
    repository.update_topic_state(student,"math.gradient",status="learning",evidence_count=1,mastery=.67)
    TopicManagement(repository.database.database_url).reference(Course.MACHINE_LEARNING, {
        "topic_id": "math.gradient", "stage": 1, "stage_title": "机器学习基础",
    })
    app = FastAPI()
    app.state.learning_repository = repository
    app.state.settings = Settings(_env_file=None)
    app.include_router(router)
    client = TestClient(app)
    headers={"Authorization":"Bearer "+account["access_token"]}
    ml = client.get("/api/v1/courses/machine_learning/outline",headers=headers).json()
    math = client.get("/api/v1/courses/advanced_mathematics/outline",headers=headers).json()
    ml_topic = next(t for group in ml["groups"] for t in group["topics"] if t["topic_id"]=="math.gradient")
    math_topic = next(t for group in math["groups"] for t in group["topics"] if t["topic_id"]=="math.gradient")
    assert ml_topic["is_reference"] and not math_topic["is_reference"]
    assert ml_topic["owner_course"] == "advanced_mathematics"
    assert ml_topic["status"] == math_topic["status"] == "learning"
    assert ml_topic["mastery"] == math_topic["mastery"] == .67
    assert not {"content_status", "has_learning_content", "readiness_reason"} & ml_topic.keys()
    assert ml["recommended_topic_id"] is not None
    assert len([g for g in ml["groups"] if g["id"].startswith("stage-")]) == 7
