from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

TopicId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$", max_length=160)]


class StageWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: int = Field(ge=1, le=999)
    stage_title: str = Field(min_length=1, max_length=100)

    @field_validator("stage_title")
    @classmethod
    def clean_stage_title(cls, value):
        if not value.strip(): raise ValueError("章节名称不能为空")
        return value.strip()


class TopicWrite(StageWrite):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    learning_objectives: list[str] = Field(default_factory=list, max_length=30)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    retrieval_keywords: list[str] = Field(default_factory=list, max_length=30)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    prerequisite_ids: list[TopicId] = Field(default_factory=list, max_length=100)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        if not value.strip(): raise ValueError("知识点名称不能为空")
        return value.strip()

    @field_validator("learning_objectives", "aliases", "retrieval_keywords")
    @classmethod
    def clean_lines(cls, values):
        if any(not value.strip() or len(value) > 500 for value in values):
            raise ValueError("每项内容需为 1 到 500 个字符")
        return list(dict.fromkeys(value.strip() for value in values))

    @field_validator("prerequisite_ids")
    @classmethod
    def unique_prerequisites(cls, values):
        if len(values) != len(set(values)): raise ValueError("前置知识点不能重复")
        return values


class ReferenceWrite(StageWrite):
    topic_id: TopicId


class TopicOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_id: str = Field(min_length=1, max_length=160)
    topic_ids: list[TopicId] = Field(min_length=1, max_length=1000)

    @field_validator("topic_ids")
    @classmethod
    def unique_topics(cls, value):
        if len(value) != len(set(value)): raise ValueError("排序中的知识点不能重复")
        return value


class StageRename(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        if not value.strip(): raise ValueError("章节名称不能为空")
        return value.strip()


class StageOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_ids: list[Annotated[str, Field(pattern=r"^stage-[1-9][0-9]*$")]] = Field(min_length=1, max_length=999)

    @field_validator("group_ids")
    @classmethod
    def unique_groups(cls, value):
        if len(value) != len(set(value)): raise ValueError("章节不能重复")
        return value
