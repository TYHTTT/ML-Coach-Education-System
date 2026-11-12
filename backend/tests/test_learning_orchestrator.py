from __future__ import annotations

from app.learning.gate import MasteryGateInput, evaluate_mastery_gate
from app.learning.orchestrator import (
    LearningOrchestratorInput,
    TopicRecommendationCandidate,
    decide_next_action,
    recommend_topic,
)


def gate(
    *,
    mastery: float = 0.85,
    attempts: int = 4,
    checkpoints: int = 1,
    checkpoint_score: float | None = 88,
    critical: int = 0,
    dimensions: frozenset[str] = frozenset({"concept", "mathematics", "mechanism"}),
):
    return evaluate_mastery_gate(
        MasteryGateInput(
            mastery=mastery,
            valid_attempt_count=attempts,
            checkpoint_count=checkpoints,
            latest_checkpoint_score=checkpoint_score,
            required_dimensions=frozenset(
                {"concept", "mathematics", "mechanism", "engineering"}
            ),
            checkpoint_dimensions=dimensions,
            unresolved_critical_misconception_count=critical,
        )
    )


def state(**overrides: object) -> LearningOrchestratorInput:
    values: dict[str, object] = {
        "current_topic_id": "ml.logistic_regression",
        "current_topic_status": "practicing",
        "current_stage": 3,
        "gate": gate(),
    }
    values.update(overrides)
    return LearningOrchestratorInput(**values)  # type: ignore[arg-type]




def test_not_started_starts_learning() -> None:
    decision = decide_next_action(state(current_topic_status="not_started"))
    assert decision.next_action == "start_learning"


def test_incomplete_teaching_continues_learning() -> None:
    decision = decide_next_action(
        state(current_topic_status="learning", teaching_complete=False)
    )
    assert decision.next_action == "continue_learning"


def test_insufficient_evidence_practices() -> None:
    decision = decide_next_action(state(gate=gate(attempts=1, mastery=0.6)))
    assert decision.next_action == "practice"
    assert "1" in decision.reasons[0] and "3" in decision.reasons[0]


def test_critical_error_remediates_before_more_practice() -> None:
    decision = decide_next_action(
        state(gate=gate(critical=1, attempts=1, mastery=0.6))
    )
    assert decision.next_action == "remediate"


def test_needs_remediation_status_is_honored_for_noncritical_errors() -> None:
    decision = decide_next_action(state(current_topic_status="needs_remediation"))
    assert decision.next_action == "remediate"


def test_sufficient_practice_takes_checkpoint() -> None:
    decision = decide_next_action(
        state(gate=gate(checkpoints=0, checkpoint_score=None))
    )
    assert decision.next_action == "take_checkpoint"


def test_failed_checkpoint_remediates() -> None:
    decision = decide_next_action(state(gate=gate(checkpoint_score=70)))
    assert decision.next_action == "remediate"


def test_passed_gate_continues_to_recommended_topic() -> None:
    candidates = (
        TopicRecommendationCandidate(
            "ml.sigmoid", "not_started", stage=3, order_index=2
        ),
    )
    decision = decide_next_action(state(gate=gate(), candidates=candidates))
    assert decision.next_action == "continue_to_next_topic"
    assert decision.recommended_topic_id == "ml.sigmoid"


def test_all_topics_mastered_completes_course() -> None:
    decision = decide_next_action(state(all_course_topics_mastered=True))
    assert decision.next_action == "course_completed"
    assert decision.recommended_topic_id is None


def test_recommendation_priority_is_deterministic() -> None:
    candidates = [
        TopicRecommendationCandidate("next-stage", "not_started", 4, 1),
        TopicRecommendationCandidate("same-stage", "not_started", 3, 3),
        TopicRecommendationCandidate("in-progress", "learning", 2, 5),
        TopicRecommendationCandidate("current", "needs_remediation", 3, 2),
    ]
    assert (
        recommend_topic(candidates, current_topic_id="current", current_stage=3)
        == "current"
    )
    assert (
        recommend_topic(candidates[:-1], current_topic_id="current", current_stage=3)
        == "in-progress"
    )
    assert (
        recommend_topic(candidates[:2], current_topic_id="current", current_stage=3)
        == "same-stage"
    )
