from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest

from app.api.dependencies import learning_repository_from_request, learning_service_from_request
from app.api.learning import router
from app.core.exceptions import AppError, StudentNotFoundError
from app.core.types import Course


class Repository:
    def student_from_token(self, token, **kwargs):
        if token != "valid-session":
            raise StudentNotFoundError()
        return {"id": "student-one"}


class LearningService:
    def __init__(self):
        self.calls = []

    def dashboard(self, **kwargs):
        self.calls.append(kwargs)
        return {"course": kwargs["course"].value, "total_topics": 1, "recent_practice": []}

    def start_topic(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": kwargs["topic_id"], "status": "learning"}


@pytest.fixture
def api():
    app = FastAPI()

    @app.exception_handler(AppError)
    async def handle(_: Request, error: AppError):
        return JSONResponse(status_code=error.status_code, content={"error": {"code": error.code}})

    service = LearningService()
    app.dependency_overrides[learning_repository_from_request] = Repository
    app.dependency_overrides[learning_service_from_request] = lambda: service
    app.include_router(router)
    with TestClient(app) as client:
        yield client, service


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/v1/learning/dashboard?course=machine_learning"),
    ("POST", "/api/v1/learning/topics/ml.machine_learning_basics/start"),
])
def test_learning_routes_require_authenticated_session(api, method, path):
    client, service = api
    assert client.request(method, path).status_code == 422
    invalid = client.request(method, path, headers={"Authorization": "Bearer invalid-session"})
    assert invalid.status_code == 404
    assert invalid.json()["error"]["code"] == "STUDENT_NOT_FOUND"
    assert service.calls == []


@pytest.mark.parametrize("course", list(Course))
def test_dashboard_passes_authenticated_student_and_selected_course(api, course):
    client, service = api
    response = client.get("/api/v1/learning/dashboard", params={"course": course.value}, headers={"Authorization": "Bearer valid-session"})
    assert response.status_code == 200
    assert response.json()["course"] == course.value
    assert service.calls == [{"student_id": "student-one", "course": course}]


def test_start_topic_uses_current_student(api):
    client, service = api
    response = client.post("/api/v1/learning/topics/math.gradient/start", headers={"Authorization": "Bearer valid-session"})
    assert response.status_code == 200
    assert response.json() == {"id": "math.gradient", "status": "learning"}
    assert service.calls == [{"student_id": "student-one", "topic_id": "math.gradient"}]
