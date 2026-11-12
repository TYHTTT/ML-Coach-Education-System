from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from app.api.admins import require_admin
from app.core.types import Course
from app.schemas.course import CreateCourseRequest, UpdateCourseRequest, CourseResponse, CourseListResponse, CourseDetailResponse
from app.services.course_repository import CourseRepository


router = APIRouter(tags=["courses"])
admin_router = APIRouter(prefix="/api/v1/admin/courses", tags=["course-management"], dependencies=[Depends(require_admin)])


def repository(request: Request) -> CourseRepository:
    return request.app.state.course_repository


@router.get("/api/v1/courses", response_model=list[CourseResponse])
def public_courses(service: CourseRepository = Depends(repository)):
    return service.list(public=True)["items"]


@admin_router.get("", response_model=CourseListResponse)
def list_courses(q: str = Query(default="", max_length=100), status: Literal["all", "active", "inactive"] = "all",
                 page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=50),
                 service: CourseRepository = Depends(repository)):
    return service.list(query=q, status=status, page=page, page_size=page_size)


@admin_router.post("", response_model=CourseResponse, status_code=201)
def create_course(payload: CreateCourseRequest, service: CourseRepository = Depends(repository)):
    return service.create(payload.model_dump())


@admin_router.get("/{course_id}", response_model=CourseDetailResponse)
def get_course(course_id: Course, service: CourseRepository = Depends(repository)):
    return service.get(course_id, detail=True)


@admin_router.patch("/{course_id}", response_model=CourseResponse)
def update_course(course_id: Course, payload: UpdateCourseRequest, service: CourseRepository = Depends(repository)):
    return service.update(course_id, payload.model_dump(exclude_unset=True))


@admin_router.delete("/{course_id}", status_code=204)
def delete_course(course_id: Course, service: CourseRepository = Depends(repository)):
    service.delete(course_id)
