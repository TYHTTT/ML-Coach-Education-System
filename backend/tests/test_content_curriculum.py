from __future__ import annotations

import pytest
import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.course_content import router
from app.core.config import Settings
from app.core.types import Course
from app.curriculum.models import CurriculumSeed
from app.curriculum.seed import seed_curriculum
from app.curriculum.validation import CurriculumCycleError, validate_curriculum
from app.services.learning_repository import LearningRepository
from app.services.learning_service import LearningService
from tests.test_curriculum import _topic


@pytest.fixture
def repository(postgres_test_database_url):
    repo = LearningRepository(postgres_test_database_url)
    seed_curriculum(repo)
    return repo


def test_global_required_cycle_rejected_but_related_network_allowed():
    ml = CurriculumSeed.model_validate({"course":"machine_learning","topics":[_topic("ml.a",1,["math.a"])]})
    mathematics = CurriculumSeed.model_validate({"course":"advanced_mathematics","topics":[_topic("math.a",1,["ml.a"])]})
    with pytest.raises(CurriculumCycleError):
        validate_curriculum([ml,mathematics])
    mathematics.topics[0].prerequisites[0].relation_type = "related"
    validate_curriculum([ml,mathematics])


def test_database_guards_global_cycle_and_registered_course(repository):
    with pytest.raises(psycopg.DatabaseError, match="cycle"):
        with repository._connect() as connection:
            connection.execute("INSERT INTO topic_prerequisites(topic_id,prerequisite_topic_id) VALUES ('la.vectors','ml.linear_regression')")
    with pytest.raises(psycopg.DatabaseError):
        with repository._connect() as connection:
            connection.execute("INSERT INTO topic_prerequisites(topic_id,prerequisite_topic_id) VALUES ('la.vectors','la.vectors')")
    with pytest.raises(psycopg.DatabaseError, match="unregistered_course"):
        with repository._connect() as connection:
            connection.execute("UPDATE curriculum_topics SET course='unregistered' WHERE id='la.vectors'")


def test_recommended_and_section_requirements_do_not_block_preview(repository):
    student = repository.register_student(username="curriculum_test", display_name="测试学生", password="test-password")["id"]
    service = LearningService(settings=Settings(_env_file=None),repository=repository)
    started = service.start_topic(student_id=student,topic_id="ml.linear_regression")
    assert started["status"] == "learning"
    assert repository.get_unmet_prerequisites(student,"ml.linear_regression")[0]["id"] == "la.dot_product"
    assert set(repository.get_prerequisite_masteries(student,"ml.linear_regression")) == {"la.dot_product"}
    assert not repository.get_unmet_prerequisites(student,"ml.dataset_split")
    assert repository.get_topic_state(student,"la.dot_product") is None


def test_local_verified_competency_reused_for_same_canonical_skill_not_whole_topic(repository):
    student = repository.register_student(username="curriculum_test", display_name="测试学生", password="test-password")["id"]
    with repository._connect() as connection:
        connection.execute("""INSERT INTO practice_sets(id,student_id,topic_id,course,mode,status,requested_difficulty,source_snapshot_json,created_at)
            VALUES ('local-test',?,'ml.linear_regression','machine_learning','practice','submitted','easy','[]','now')""", (student,))
        connection.execute("""INSERT INTO prerequisite_verifications
            VALUES (?, 'ml.linear_regression', 'la.dot_product', 'la.dot_product.foundation', 'content-v1', 'local-test', 'now')""", (student,))
    assert repository.get_unmet_prerequisites(student,"ml.linear_regression") == []
    assert repository.get_prerequisite_masteries(student,"ml.linear_regression") == {"la.dot_product":1.0}
    assert not any(edge["id"]=="la.dot_product" for edge in repository.get_unmet_prerequisites(student,"ml.logistic_regression"))
    assert any(edge["id"]=="ml.sigmoid" for edge in repository.get_unmet_prerequisites(student,"ml.logistic_regression"))
    assert repository.get_topic_state(student,"la.dot_product") is None
    # A genuinely different competency or new rule version still needs proof.
    with repository._connect() as connection:
        connection.execute("UPDATE topic_prerequisites SET required_competencies_json='[\"la.dot_product.matrix_path\"]' WHERE topic_id='ml.logistic_regression' AND prerequisite_topic_id='la.dot_product'")
    assert any(edge["id"]=="la.dot_product" for edge in repository.get_unmet_prerequisites(student,"ml.logistic_regression"))
    with repository._connect() as connection:
        connection.execute("UPDATE topic_prerequisites SET rule_version='content-v2' WHERE topic_id='ml.linear_regression' AND prerequisite_topic_id='la.dot_product'")
    assert repository.get_unmet_prerequisites(student,"ml.linear_regression")


def test_canonical_outline_shares_state_without_local_content_requirements(repository):
    account = repository.register_student(username="outline_test", display_name="测试学生", password="test-password")
    student = account["id"]
    repository.update_topic_state(student,"math.gradient",status="learning",evidence_count=1,mastery=.67)
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


def test_core_required_closure_has_only_ready_candidate_topics(repository):
    core = {"la.vectors","la.dot_product","la.matrix_multiplication","prob.basics","prob.conditional_probability","prob.distributions","prob.expectation_variance","prob.bernoulli","math.functions","math.exponential_logarithmic","math.derivative_definition","math.derivative_rules","math.chain_rule","math.partial_derivatives","math.gradient","ml.linear_regression","ml.gradient_descent","ml.logistic_regression","ml.cross_entropy","ml.sigmoid"}
    for topic_id in core:
        required = {p["id"] for p in repository.list_prerequisites(topic_id) if p["relation_type"]=="required" and p["scope"]=="topic"}
        assert required <= core
