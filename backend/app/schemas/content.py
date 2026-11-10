"""Versioned instructional content and deliberately separate student projections."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
class ContentModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Formula(ContentModel):
    expression: str
    symbols: str
    conditions: str

class Lesson(ContentModel):
    id: str
    topic_id: str
    title: str
    learning_objectives: list[str] = Field(min_length=1)
    prerequisite_summary: str
    motivating_problem: str = Field(min_length=1)
    key_concepts: list[str] = Field(min_length=1)
    formulas: list[Formula]
    worked_example_ids: list[str] = Field(min_length=1)
    practice_recommendations: list[str]
    summary: str
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    content_origin: Literal['source_derived','instructor_authored','generated_draft']
    version: int = Field(default=1, ge=1)
    status: Literal['draft','published','archived'] = 'draft'

class ExampleStep(ContentModel):
    step_id: str
    title: str
    explanation: str = Field(min_length=1)
    formula: str = ''
    substitution: str = ''
    result: str = ''
    justification: str = Field(min_length=1)

class WorkedExample(ContentModel):
    id: str
    topic_id: str
    title: str
    difficulty: Literal['easy','medium','hard']
    problem: str
    givens: dict[str, Any]
    target: str
    solution_outline: str
    steps: list[ExampleStep] = Field(min_length=2)
    final_answer: str
    verification: dict[str, Any]
    common_mistakes: list[str]
    followup_practice_ids: list[str]
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    content_origin: Literal['source_derived','instructor_authored','generated_draft']
    version: int = Field(default=1,ge=1)
    status: Literal['draft','published','archived'] = 'draft'
    family_id: str

class PrerequisiteTestRequest(ContentModel):
    topic_id: str
    prerequisite_topic_id: str | None = None
    question_count: int = Field(default=3,ge=3,le=5)

class ExampleAsk(ContentModel):
    version: int = Field(ge=1)
    step_id: str
    question: str = Field(default='为什么这一步可以这样做？',min_length=1,max_length=2000)

class ExampleExposure(ContentModel):
    version: int = Field(ge=1)
