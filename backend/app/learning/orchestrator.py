"""A deterministic, non-LLM supervisor for the Phase 2 learning loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from app.schemas.learning import (
    LearningDecision,
    LearningStatus,
    MasteryGateResult,
)


_STARTED_INCOMPLETE = frozenset(
    {"learning", "practicing", "needs_remediation", "ready_for_checkpoint"}
)
_VALID_STATUSES = frozenset(
    {
        "not_started",
        "learning",
        "practicing",
        "needs_remediation",
        "ready_for_checkpoint",
        "mastered",
    }
)


@dataclass(frozen=True, slots=True)
class TopicRecommendationCandidate:
    topic_id: str
    status: LearningStatus
    stage: int
    order_index: int

    def __post_init__(self) -> None:
        if not self.topic_id.strip():
            raise ValueError("topic_id must not be empty")
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"unsupported learning status: {self.status}")
        if self.stage < 0 or self.order_index < 0:
            raise ValueError("stage and order_index must not be negative")


@dataclass(frozen=True, slots=True)
class LearningOrchestratorInput:
    current_topic_id: str
    current_topic_status: LearningStatus
    current_stage: int
    gate: MasteryGateResult
    all_course_topics_mastered: bool = False
    teaching_complete: bool = True
    candidates: tuple[TopicRecommendationCandidate, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.current_topic_id.strip():
            raise ValueError("current_topic_id must not be empty")
        if self.current_topic_status not in _VALID_STATUSES:
            raise ValueError(
                f"unsupported learning status: {self.current_topic_status}"
            )
        if self.current_stage < 0:
            raise ValueError("current_stage must not be negative")


def recommend_topic(
    candidates: Iterable[TopicRecommendationCandidate],
    *,
    current_topic_id: str,
    current_stage: int,
) -> str | None:
    """Apply the documented topic recommendation priority deterministically."""

    topics = list(candidates)
    current = next((item for item in topics if item.topic_id == current_topic_id), None)
    if current is not None and current.status == "needs_remediation":
        return current.topic_id

    started = sorted(
        (item for item in topics if item.status in _STARTED_INCOMPLETE),
        key=lambda item: (item.stage, item.order_index, item.topic_id),
    )
    if started:
        return started[0].topic_id

    same_stage = sorted(
        (
            item
            for item in topics
            if item.status == "not_started" and item.stage == current_stage
        ),
        key=lambda item: (item.order_index, item.topic_id),
    )
    if same_stage:
        return same_stage[0].topic_id

    next_stages = sorted(
        (
            item
            for item in topics
            if item.status == "not_started" and item.stage > current_stage
        ),
        key=lambda item: (item.stage, item.order_index, item.topic_id),
    )
    return next_stages[0].topic_id if next_stages else None


def decide_next_action(state: LearningOrchestratorInput) -> LearningDecision:
    """Choose the next learning action from explicit state only.

    The function neither calls an LLM nor mutates/persists status.  The caller is
    responsible for marking a topic mastered after a passed Gate.
    """

    if state.all_course_topics_mastered:
        return LearningDecision(
            next_action="course_completed",
            reasons=["当前课程的全部知识点均已通过 Mastery Gate"],
            recommended_topic_id=None,
        )

    if state.current_topic_status == "not_started":
        return LearningDecision(
            next_action="start_learning",
            reasons=["当前知识点尚未开始学习"],
            recommended_topic_id=state.current_topic_id,
        )

    requirements = state.gate.requirements
    if not requirements.critical_misconceptions.passed:
        return LearningDecision(
            next_action="remediate",
            reasons=[
                f"仍有 {requirements.critical_misconceptions.current} 个未解决的关键错误"
            ],
            recommended_topic_id=state.current_topic_id,
        )

    if state.current_topic_status == "needs_remediation":
        return LearningDecision(
            next_action="remediate",
            reasons=["当前知识点存在尚未解决的错误，需要先完成针对性补救"],
            recommended_topic_id=state.current_topic_id,
        )

    if state.current_topic_status == "learning" and not state.teaching_complete:
        return LearningDecision(
            next_action="continue_learning",
            reasons=["当前知识点的基础讲解尚未完成"],
            recommended_topic_id=state.current_topic_id,
        )

    if not requirements.valid_attempts.passed:
        return LearningDecision(
            next_action="practice",
            reasons=[
                "当前有效练习次数为 "
                f"{requirements.valid_attempts.current}，至少需要 "
                f"{requirements.valid_attempts.required} 次"
            ],
            recommended_topic_id=state.current_topic_id,
        )

    if not requirements.checkpoint_completed.passed:
        return LearningDecision(
            next_action="take_checkpoint",
            reasons=["有效练习证据已经足够，尚未完成知识点 checkpoint"],
            recommended_topic_id=state.current_topic_id,
        )

    if not requirements.checkpoint_score.passed:
        return LearningDecision(
            next_action="remediate",
            reasons=[
                "最近一次 checkpoint 得分为 "
                f"{requirements.checkpoint_score.current}，要求至少为 "
                f"{requirements.checkpoint_score.required}"
            ],
            recommended_topic_id=state.current_topic_id,
        )

    if state.gate.passed:
        recommended = recommend_topic(
            (
                item
                for item in state.candidates
                if item.topic_id != state.current_topic_id
            ),
            current_topic_id=state.current_topic_id,
            current_stage=state.current_stage,
        )
        return LearningDecision(
            next_action="continue_to_next_topic",
            reasons=["当前知识点已经满足全部 Mastery Gate 条件"],
            recommended_topic_id=recommended,
        )

    reasons: list[str] = []
    if not requirements.mastery_threshold.passed:
        reasons.append(
            "当前掌握度为 "
            f"{float(requirements.mastery_threshold.current or 0):.2f}，要求至少为 "
            f"{float(requirements.mastery_threshold.required):.2f}"
        )
    if not requirements.dimension_coverage.passed:
        reasons.append(
            "checkpoint 当前覆盖 "
            f"{requirements.dimension_coverage.current} 个必需维度，至少需要 "
            f"{requirements.dimension_coverage.required} 个"
        )
    if not reasons:
        reasons.append("需要继续积累有效学习证据")
    return LearningDecision(
        next_action="practice",
        reasons=reasons,
        recommended_topic_id=state.current_topic_id,
    )
