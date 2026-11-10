from __future__ import annotations
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.dependencies import (
    evaluation_service_from_request,
    learning_repository_from_request,
    learning_service_from_request,
    practice_service_from_request,
    remediation_service_from_request,
)
from app.api.learning import router as learning_router
from app.api.practice import router as practice_router
from app.core.exceptions import AppError, StudentNotFoundError
from app.schemas.practice import PracticeQuestionPublic
from app.schemas.practice_api import PracticeSetResponse, RemediationResponse


STUDENT_ID = "6ab2192e-e096-4018-bc08-f452230c5ca7"


class FakeRepository:
    def __init__(self) -> None:
        self.unmet = []
        self.status = "learning"

    def student_from_token(self, student_id, **kwargs):
        return self.require_student(student_id, **kwargs)

    def require_student(self, student_id, **kwargs):
        if student_id != STUDENT_ID:
            raise StudentNotFoundError()
        return {"id": student_id}

    def require_topic(self, topic_id, **kwargs):
        return {
            "id": topic_id,
            "course": "machine_learning",
            "title": "逻辑回归",
        }

    def get_unmet_prerequisites(self, student_id, topic_id):
        return self.unmet

    def get_topic_state(self, student_id, topic_id):
        return {"status": self.status}


class FakePracticeService:
    async def create_set(self, *, student_id, request):
        return PracticeSetResponse(
            practice_set_id="set-1",
            topic_id=request.topic_id,
            mode=request.mode,
            questions=[
                PracticeQuestionPublic(
                    question_id="q1",
                    question_type="concept_explanation",
                    difficulty="medium",
                    question="为什么使用交叉熵？",
                    options=None,
                    dimensions=["concept"],
                    position=1,
                    max_score=100,
                )
            ],
            source_summary=[
                {"source_id": "S1", "source_file": "course.md", "title": "分类"}
            ],
        )

    def get_set(self, *, student_id, practice_set_id):
        raise AssertionError("not used")


class FakeEvaluationService:
    async def submit(self, **kwargs):
        raise AssertionError("not used")


class FakeLearningService:
    def evaluate_topic_gate(self, student_id, topic, state):
        return SimpleNamespace(next_action="practice")

    def dashboard(self, *, student_id, course):
        return {
            "course": course.value,
            "total_topics": 1,
            "mastered_count": 0,
            "learning_count": 1,
            "not_started_count": 0,
            "locked_count": 0,
            "current_topic": None,
            "recommended_topic_id": "ml.logistic_regression",
            "next_action": "practice",
            "reasons": ["继续积累证据"],
            "recent_practice": [],
            "stages": [],
        }

    def start_topic(self, *, student_id, topic_id):
        return {"id": topic_id, "course": "machine_learning", "status": "learning"}

    def topic_detail(self, *, student_id, topic_id):
        return {"id": topic_id, "course": "machine_learning", "status": "learning"}

    def history(self, *, student_id, course, limit):
        return {"course": course.value, "events": []}


class FakeRemediationService:
    async def create(self, *, student_id, topic_id, attempt_id):
        return RemediationResponse(
            topic_id=topic_id,
            diagnosis="错误诊断",
            explanation="正确解释",
            contrast_example="对比例子",
            targeted_question_set_id="target-set",
            sources=[],
        )


def _client(repository: FakeRepository | None = None) -> tuple[TestClient, FakeRepository]:
    repository = repository or FakeRepository()
    app = FastAPI()

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    app.include_router(practice_router)
    app.include_router(learning_router)
    app.dependency_overrides[learning_repository_from_request] = lambda: repository
    app.dependency_overrides[practice_service_from_request] = FakePracticeService
    app.dependency_overrides[evaluation_service_from_request] = FakeEvaluationService
    app.dependency_overrides[learning_service_from_request] = FakeLearningService
    app.dependency_overrides[remediation_service_from_request] = FakeRemediationService
    return TestClient(app), repository


def test_practice_endpoint_requires_backend_student_header() -> None:
    client, _ = _client()
    response = client.post(
        "/api/v1/practice/sets",
        json={"topic_id": "ml.logistic_regression", "mode": "practice", "count": 1},
    )
    assert response.status_code == 422

    response = client.post(
        "/api/v1/practice/sets",
        headers={"Authorization": "Bearer 2f37cace-c396-4545-991c-27bf8f61f5cc"},
        json={"topic_id": "ml.logistic_regression", "mode": "practice", "count": 1},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "STUDENT_NOT_FOUND"


def test_practice_public_response_has_no_hidden_grading_material() -> None:
    client, _ = _client()
    response = client.post(
        "/api/v1/practice/sets",
        headers={"Authorization": f"Bearer {STUDENT_ID}"},
        json={"topic_id": "ml.logistic_regression", "mode": "practice", "count": 1},
    )
    assert response.status_code == 201
    body = response.text
    assert "answer_key" not in body
    assert "rubric" not in body
    assert "canonical_answer" not in body


def test_practice_preview_allowed_but_early_checkpoint_rejected() -> None:
    repository = FakeRepository()
    repository.unmet = [{"id": "ml.basics", "title": "机器学习基础"}]
    client, _ = _client(repository)
    response = client.post(
        "/api/v1/practice/sets",
        headers={"Authorization": f"Bearer {STUDENT_ID}"},
        json={"topic_id": "ml.logistic_regression", "mode": "practice", "count": 1},
    )
    assert response.status_code == 201
    blocked = client.post('/api/v1/practice/sets',headers={'Authorization':f'Bearer {STUDENT_ID}'},
        json={'topic_id':'ml.logistic_regression','mode':'checkpoint','count':5})
    assert blocked.status_code == 409
    repository.unmet = []
    repository.status = "practicing"
    response = client.post(
        "/api/v1/practice/sets",
        headers={"Authorization": f"Bearer {STUDENT_ID}"},
        json={"topic_id": "ml.logistic_regression", "mode": "checkpoint", "count": 5},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TOPIC_LOCKED"


def test_learning_course_topic_mismatch_and_remediation_route() -> None:
    client, _ = _client()
    mismatch = client.get(
        "/api/learning/advanced_mathematics/topics/ml.logistic_regression",
        headers={"Authorization": f"Bearer {STUDENT_ID}"},
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "COURSE_TOPIC_MISMATCH"

    remediation = client.post(
        "/api/v1/learning/remediation",
        headers={"Authorization": f"Bearer {STUDENT_ID}"},
        json={"topic_id": "ml.logistic_regression", "attempt_id": "attempt-1"},
    )
    assert remediation.status_code == 200
    assert remediation.json()["targeted_question_set_id"] == "target-set"


def test_required_phase_two_routes_are_registered() -> None:
    paths = {
        route.path
        for route in [*practice_router.routes, *learning_router.routes]
        if getattr(route, "path", None) is not None
    }
    assert "/api/v1/practice/sets" in paths
    assert "/api/v1/practice/sets/{practice_set_id}" in paths
    assert "/api/v1/practice/sets/{practice_set_id}/submit" in paths
    assert "/api/v1/learning/dashboard" in paths
    assert "/api/v1/learning/topics/{topic_id}/start" in paths
    assert "/api/v1/learning/remediation" in paths
    assert "/api/v1/learning/history" in paths
