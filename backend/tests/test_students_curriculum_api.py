from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.curriculum import router as curriculum_router
from app.api.students import router as students_router
from app.curriculum.seed import seed_curriculum
from app.services.learning_repository import LearningRepository, StudentNotFoundError


def _client(postgres_test_database_url) -> tuple[TestClient, LearningRepository]:
    repository = LearningRepository(postgres_test_database_url)
    seed_curriculum(repository)
    app = FastAPI()
    app.state.learning_repository = repository
    app.include_router(students_router)
    app.include_router(curriculum_router)
    return TestClient(app), repository


def test_registered_student_can_login_and_logout(postgres_test_database_url) -> None:
    client, repository = _client(postgres_test_database_url)
    response = client.post("/api/v1/students/register", json={"username": "test_user", "password": "test-password", "display_name": "测试学生"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["student_id"]
    assert repository.get_student(payload["student_id"]) is not None
    logged_in = client.post("/api/v1/students/login", json={"username": "test_user", "password": "test-password"})
    assert logged_in.status_code == 200
    token = logged_in.json()["access_token"]
    assert token != payload["access_token"]
    assert repository.student_from_token(token)["id"] == payload["student_id"]
    assert client.post("/api/v1/students/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 204
    import pytest
    with pytest.raises(StudentNotFoundError):
        repository.student_from_token(token)


def test_missing_student_is_rejected(postgres_test_database_url) -> None:
    _, repository = _client(postgres_test_database_url)

    try:
        repository.require_student("6ab2192e-e096-4018-bc08-f452230c5ca7")
    except StudentNotFoundError as exc:
        assert exc.code == "STUDENT_NOT_FOUND"
    else:
        raise AssertionError("missing student should be rejected")


def test_learning_request_touches_last_active_at(postgres_test_database_url, monkeypatch) -> None:
    client, repository = _client(postgres_test_database_url)
    monkeypatch.setattr(
        LearningRepository,
        "_now",
        staticmethod(lambda: "2026-09-01T10:00:00+00:00"),
    )
    student = repository.register_student(username="test_user", password="test-password", display_name="测试学生")
    monkeypatch.setattr(
        LearningRepository,
        "_now",
        staticmethod(lambda: "2026-09-01T10:05:00+00:00"),
    )

    response = client.get(
        "/api/v1/curriculum/topics",
        params={"course": "machine_learning"},
        headers={"Authorization": "Bearer " + student["access_token"]},
    )

    assert response.status_code == 200
    assert repository.get_student(student["id"])["last_active_at"] == (
        "2026-09-01T10:05:00+00:00"
    )


def test_curriculum_response_hides_unstarted_beta_prior(postgres_test_database_url) -> None:
    client, repository = _client(postgres_test_database_url)
    student = repository.register_student(username="test_user", password="test-password", display_name="测试学生")

    response = client.get(
        "/api/v1/curriculum/topics",
        params={"course": "machine_learning"},
        headers={"Authorization": "Bearer " + student["access_token"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["course"] == "machine_learning"
    first = payload["stages"][0]["topics"][0]
    second = payload["stages"][0]["topics"][1]
    assert first["status"] == "not_started"
    assert first["mastery"] is None
    assert first["mastery_display"] is None
    assert second["status"] == "not_started"
    assert second["locked_reason"] is None


def test_topic_detail_exposes_objectives_and_empty_dimension_state(postgres_test_database_url) -> None:
    client, repository = _client(postgres_test_database_url)
    student = repository.register_student(username="test_user", password="test-password", display_name="测试学生")

    response = client.get(
        "/api/v1/curriculum/topics/ml.logistic_regression",
        headers={"Authorization": "Bearer " + student["access_token"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "ml.logistic_regression"
    assert payload["learning_objectives"]
    assert payload["required_dimensions"] == [
        "concept",
        "mathematics",
        "mechanism",
        "engineering",
        "application",
    ]
    assert all(item["mastery"] is None for item in payload["dimensions"])
