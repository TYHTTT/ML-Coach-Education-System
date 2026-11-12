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

    course: Course | None = None
    # The route applies the configured MAX_MESSAGE_LENGTH. This is only an
    # absolute safety ceiling so deployments may choose a value above 8,000.
    message: str = Field(min_length=1, max_length=100_000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=100)
    topic_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")
    conversation_token: str | None = Field(default=None, min_length=1, max_length=2048)
    learning_mode: Literal["free_qa", "topic_teaching", "topic_clarification", "topic_practice", "topic_answer"] = "free_qa"

    @model_validator(mode="after")
    def learning_requires_topic(self) -> "ChatRequest":
        if self.course is None and (self.topic_id is not None or self.learning_mode != "free_qa"):
            raise ValueError("课程学习需要指定 course，自由问答可以不指定课程")
        if self.learning_mode != "free_qa" and self.topic_id is None:
            raise ValueError("继续知识点学习需要指定当前知识点 topic_id")
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
    course: Course | None = None
    sources: list[SourceResponse]
    retrieval_count: int
    conversation_token: str | None = None
