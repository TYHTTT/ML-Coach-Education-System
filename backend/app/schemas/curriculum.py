from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.core.types import Course


TopicStatus = Literal[
    "not_started",
    "learning",
    "practicing",
    "needs_remediation",
    "ready_for_checkpoint",
    "mastered",
]


class TopicSummaryResponse(BaseModel):
    id: str
    slug: str
    title: str
    order_index: int
    description: str
    status: TopicStatus | None = None
    mastery: float | None = None
    mastery_display: str | None = None
    confidence: float | None = None


class CurriculumStageResponse(BaseModel):
    stage: int
    title: str
    topics: list[TopicSummaryResponse]


class CurriculumResponse(BaseModel):
    course: Course
    stages: list[CurriculumStageResponse]


class DimensionStateResponse(BaseModel):
    dimension: str
    mastery: float | None = None
    mastery_display: str | None = None
    confidence: float | None = None
    evidence_count: int = 0


class TopicDetailResponse(TopicSummaryResponse):
    course: Course
    stage: int
    stage_title: str
    learning_objectives: list[str]
    aliases: list[str]
    retrieval_keywords: list[str]
    difficulty: Literal["easy", "medium", "hard"]
    required_dimensions: list[str]
    dimensions: list[DimensionStateResponse]
    active: bool
    created_at: datetime
    updated_at: datetime
