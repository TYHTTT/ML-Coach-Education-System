from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.core.types import Course


class CourseFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    active: bool = True
    sort_order: int = Field(default=0, ge=0, le=99999)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        if not value.strip():
            raise ValueError("课程名称不能为空")
        return value.strip()


class CreateCourseRequest(CourseFields):
    id: Course


class UpdateCourseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=99999)

    @model_validator(mode="after")
    def check_update(self):
        if not self.model_fields_set or any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("请提供需要修改的课程信息，字段不能为 null")
        if self.title is not None:
            if not self.title.strip():
                raise ValueError("课程名称不能为空")
            self.title = self.title.strip()
        return self


class CourseResponse(BaseModel):
    id: str
    title: str
    description: str
    active: bool
    sort_order: int
    topic_count: int
    stage_count: int
    created_at: datetime
    updated_at: datetime


class CourseListResponse(BaseModel):
    items: list[CourseResponse]
    total: int
    page: int
    page_size: int


class CourseTopicResponse(BaseModel):
    id: str
    title: str
    stage: int
    stage_title: str
    active: bool


class CourseDetailResponse(CourseResponse):
    topics: list[CourseTopicResponse]
