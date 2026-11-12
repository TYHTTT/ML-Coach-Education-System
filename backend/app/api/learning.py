from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.dependencies import learning_service_from_request, require_student_from_header
from app.core.types import Course
from app.services.learning_service import LearningService


router = APIRouter(prefix="/api/v1/learning", tags=["learning"])


@router.get("/dashboard")
def learning_dashboard(
    course: Course,
    student: dict = Depends(require_student_from_header),
    service: LearningService = Depends(learning_service_from_request),
) -> dict[str, Any]:
    return service.dashboard(student_id=student["id"], course=course)


@router.post("/topics/{topic_id}/start")
def start_topic(
    topic_id: str,
    student: dict = Depends(require_student_from_header),
    service: LearningService = Depends(learning_service_from_request),
) -> dict[str, Any]:
    return service.start_topic(student_id=student["id"], topic_id=topic_id)
