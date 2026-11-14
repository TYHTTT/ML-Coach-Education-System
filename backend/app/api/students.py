from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from app.schemas.student import (
    AuthenticatedStudentResponse,
    CurrentStudentResponse,
    LoginRequest,
    RegisterStudentRequest,
)
from app.services.learning_repository import LearningRepository


router = APIRouter(prefix="/api/v1/students", tags=["students"])


def learning_repository_from_request(request: Request) -> LearningRepository:
    return request.app.state.learning_repository


def _bearer_token(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="无效的登录凭据")
    return token


def _auth_response(student: dict) -> AuthenticatedStudentResponse:
    return AuthenticatedStudentResponse(
        student_id=student["id"],
        username=student["username"],
        display_name=student["display_name"],
        access_token=student["access_token"],
        created_at=student["created_at"],
    )


@router.post("/register", response_model=AuthenticatedStudentResponse, status_code=201)
def register_student(
    payload: RegisterStudentRequest, request: Request
) -> AuthenticatedStudentResponse:
    try:
        return _auth_response(
            learning_repository_from_request(request).register_student(
                **payload.model_dump()
            )
        )
    except ValueError as exc:
        if str(exc) == "username_taken":
            raise HTTPException(status_code=409, detail="用户名已被使用") from exc
        raise


@router.post("/login", response_model=AuthenticatedStudentResponse)
def login_student(
    payload: LoginRequest, request: Request
) -> AuthenticatedStudentResponse:
    student = learning_repository_from_request(request).authenticate_student(
        **payload.model_dump()
    )
    if student is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return _auth_response(student)


@router.get("/me", response_model=CurrentStudentResponse)
def current_student(
    request: Request, authorization: str = Header(..., alias="Authorization")
) -> CurrentStudentResponse:
    student = learning_repository_from_request(request).student_from_token(
        _bearer_token(authorization)
    )
    return CurrentStudentResponse(
        student_id=student["id"],
        username=student["username"],
        display_name=student["display_name"],
        created_at=student["created_at"],
    )


@router.post("/logout", status_code=204)
def logout_student(
    request: Request, authorization: str = Header(..., alias="Authorization")
) -> None:
    learning_repository_from_request(request).revoke_session(
        _bearer_token(authorization)
    )
