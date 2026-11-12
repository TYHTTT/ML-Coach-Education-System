from __future__ import annotations

from fastapi import Depends, Header, Request

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.services.learning_repository import LearningRepository
from app.services.learning_service import LearningService


def settings_from_request(request: Request) -> Settings:
    return request.app.state.settings


def agent_from_request(request: Request):
    request_llm_client = getattr(request.state, "llm_client", None)
    if request_llm_client is not None:
        return request_llm_client
    if request.app.state.llm_client is not None:
        return request.app.state.llm_client
    raise ConfigurationError("请在后端配置 Dify Agent 服务")


def learning_repository_from_request(request: Request) -> LearningRepository:
    """Return the single application-wide learning persistence boundary."""

    return request.app.state.learning_repository


def require_student_from_header(
    authorization: str = Header(..., alias="Authorization"),
    repository: LearningRepository = Depends(learning_repository_from_request),
) -> dict:
    """Resolve the authenticated student from the opaque Bearer session token."""

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        from app.core.exceptions import StudentNotFoundError
        raise StudentNotFoundError()
    return repository.student_from_token(token, touch=True)


def student_id_from_authorization(
    authorization: str | None,
    repository: LearningRepository,
    *,
    touch: bool = True,
) -> str | None:
    """Return a session's internal student ID, preserving anonymous read routes."""

    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        from app.core.exceptions import StudentNotFoundError
        raise StudentNotFoundError()
    return repository.student_from_token(token, touch=touch)["id"]


def learning_service_from_request(
    settings: Settings = Depends(settings_from_request),
    repository: LearningRepository = Depends(learning_repository_from_request),
) -> LearningService:
    return LearningService(settings=settings, repository=repository)
