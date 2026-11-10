from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.types import Course


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("历史消息不能为空")
        return value


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course: Course
    # The route applies the configured MAX_MESSAGE_LENGTH. This is only an
    # absolute safety ceiling so deployments may choose a value above 8,000.
    message: str = Field(min_length=1, max_length=100_000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=100)
    topic_id: str | None = Field(default=None, pattern=r"^(?:ml|math|la|prob)\.[a-z0-9_]+$")
    learning_mode: Literal["free_qa", "topic_teaching", "topic_clarification", "worked_example", "remediation"] = "free_qa"

    @model_validator(mode="after")
    def example_requires_topic(self) -> "ChatRequest":
        if self.learning_mode == "worked_example" and self.topic_id is None:
            raise ValueError("生成学习例题需要指定当前知识点 topic_id")
        if self.learning_mode == "topic_clarification" and self.topic_id is None:
            raise ValueError("补充讲解需要指定当前知识点 topic_id")
        return self

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("问题不能为空")
        return value


class SourceResponse(BaseModel):
    source_id: str
    source_course: Course | None = None
    topic_id: str | None = None
    document_id: str
    source_file: str
    title: str | None = None
    chapter: str | None = None
    section: str | None = None
    page: int | None = None
    chunk_index: int
    snippet: str
    distance: float | None = None


class ChatResponse(BaseModel):
    answer: str
    course: Course
    sources: list[SourceResponse]
    retrieval_count: int
