"""Read-only historical progress and recommendation contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


LearningStatus = Literal[
    "locked",
    "not_started",
    "learning",
    "practicing",
    "needs_remediation",
    "ready_for_checkpoint",
    "mastered",
]
LearningAction = Literal[
    "study_prerequisite",
    "start_learning",
    "continue_learning",
    "practice",
    "remediate",
    "take_checkpoint",
    "continue_to_next_topic",
    "course_completed",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequirementStatus(StrictModel):
    passed: bool
    current: float | int | bool | None
    required: float | int | bool
    details: list[str] = Field(default_factory=list)


class MasteryGateRequirements(StrictModel):
    mastery_threshold: RequirementStatus
    valid_attempts: RequirementStatus
    checkpoint_completed: RequirementStatus
    checkpoint_score: RequirementStatus
    dimension_coverage: RequirementStatus
    critical_misconceptions: RequirementStatus
    prerequisites_mastered: RequirementStatus


class MasteryGateResult(StrictModel):
    passed: bool
    mastery: float = Field(ge=0, le=1, allow_inf_nan=False)
    requirements: MasteryGateRequirements
    next_action: LearningAction


class LearningDecision(StrictModel):
    next_action: LearningAction
    reasons: list[str] = Field(min_length=1)
    recommended_topic_id: str | None = None

    @field_validator("reasons")
    @classmethod
    def clean_reasons(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("reasons must not contain empty values")
        return cleaned
