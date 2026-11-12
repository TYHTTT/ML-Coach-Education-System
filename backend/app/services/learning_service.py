from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.core.types import Course
from app.learning.gate import MasteryGateConfig, MasteryGateInput, evaluate_mastery_gate
from app.learning.orchestrator import (
    LearningOrchestratorInput,
    TopicRecommendationCandidate,
    decide_next_action,
)
from app.services.learning_repository import LearningRepository


class LearningService:
    """Study state and course overview, including historical progress recommendations."""

    def __init__(self, *, settings: Settings, repository: LearningRepository) -> None:
        self.settings = settings
        self.repository = repository

    def start_topic(self, *, student_id: str, topic_id: str) -> dict[str, Any]:
        self.repository.require_student(student_id)
        topic = self.repository.require_topic(topic_id, student_id=student_id)
        state = self.repository.ensure_topic_state(student_id, topic_id)
        if state["status"] != "mastered":
            changes: dict[str, Any] = {"status": "learning"}
            if not state.get("started_at"):
                changes["started_at"] = self.repository._now()
            state = self.repository.update_topic_state(student_id, topic_id, **changes)
        self.repository.create_learning_session(
            student_id=student_id,
            course=topic["course"],
            topic_id=topic_id,
            state="learning",
        )
        return self.topic_detail(student_id=student_id, topic_id=topic_id)

    def topic_detail(self, *, student_id: str, topic_id: str) -> dict[str, Any]:
        self.repository.require_student(student_id)
        topic = self.repository.require_topic(topic_id, student_id=student_id)
        state = self.repository.get_topic_state(student_id, topic_id)
        unmet = self.repository.get_unmet_prerequisites(student_id, topic_id)
        status = self._status(state)
        dimensions = {
            item["dimension"]: {
                "mastery": float(item["mastery"]),
                "confidence": float(item["confidence"]),
                "evidence_count": int(item["evidence_count"]),
            }
            for item in self.repository.list_dimension_states(student_id, topic_id)
        }
        for dimension in topic.get("required_dimensions", []):
            dimensions.setdefault(
                dimension,
                {"mastery": None, "confidence": 0.0, "evidence_count": 0},
            )
        return {
            **{key: value for key, value in topic.items() if not key.startswith("state_")},
            "status": status,
            "mastery": (
                float(state["mastery"])
                if state is not None and int(state["evidence_count"]) > 0
                else None
            ),
            "mastery_display": (
                f"{float(state['mastery']) * 100:.0f}%"
                if state is not None and int(state["evidence_count"]) > 0
                else "尚未评估"
            ),
            "confidence": float(state["confidence"]) if state else 0.0,
            "dimensions": dimensions,
            "locked_reason": (
                "建议先学习：" + "、".join(item["title"] for item in unmet)
                if unmet
                else None
            ),
        }

    def dashboard(self, *, student_id: str, course: Course) -> dict[str, Any]:
        self.repository.require_student(student_id)
        topics = self.repository.list_topics(course, student_id=student_id)
        prerequisite_statuses = self.repository.prerequisite_statuses(
            student_id, [topic["id"] for topic in topics]
        )
        views: list[dict[str, Any]] = []
        for topic in topics:
            state = (
                {
                    "status": topic["state_status"],
                    "mastery": topic["state_mastery"],
                    "confidence": topic["state_confidence"],
                    "evidence_count": topic["state_evidence_count"],
                }
                if topic["state_status"] is not None
                else None
            )
            unmet = [
                item for item in prerequisite_statuses[topic["id"]]
                if item["relation_type"] == "required" and item["scope"] == "topic" and not item["satisfied"]
            ]
            views.append(
                {
                    "id": topic["id"],
                    "title": topic["title"],
                    "stage": topic["stage"],
                    "stage_title": topic["stage_title"],
                    "order_index": topic["order_index"],
                    "status": self._status(state),
                    "mastery": (
                        float(state["mastery"])
                        if state is not None and int(state["evidence_count"]) > 0
                        else None
                    ),
                    "confidence": float(state["confidence"]) if state else 0.0,
                    "unmet_prerequisites": [item["id"] for item in unmet],
                }
            )
        current = self._current_topic(views)
        if current is None:
            decision = {
                "next_action": "course_completed",
                "reasons": ["当前课程的全部知识点均已通过 Mastery Gate"],
                "recommended_topic_id": None,
            }
        else:
            topic = next(item for item in topics if item["id"] == current["id"])
            state = self.repository.get_topic_state(student_id, current["id"])
            gate = self.evaluate_topic_gate(student_id, topic, state)
            candidates = tuple(
                TopicRecommendationCandidate(
                    topic_id=item["id"],
                    status=item["status"],
                    stage=int(item["stage"]),
                    order_index=int(item["order_index"]),
                    unlocked=item["status"] != "locked",
                )
                for item in views
            )
            decision = decide_next_action(
                LearningOrchestratorInput(
                    current_topic_id=current["id"],
                    current_topic_status=current["status"],
                    current_stage=int(current["stage"]),
                    gate=gate,
                    all_course_topics_mastered=all(
                        item["status"] == "mastered" for item in views
                    ),
                    unmet_prerequisite_ids=tuple(current["unmet_prerequisites"]),
                    candidates=candidates,
                )
            ).model_dump()
        counts = {
            status: sum(item["status"] == status for item in views)
            for status in (
                "mastered",
                "learning",
                "practicing",
                "needs_remediation",
                "ready_for_checkpoint",
                "not_started",
                "locked",
            )
        }
        stages: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for view in views:
            stages.setdefault((view["stage"], view["stage_title"]), []).append(view)
        return {
            "course": course.value,
            "total_topics": len(views),
            "mastered_count": counts["mastered"],
            "learning_count": sum(
                counts[item]
                for item in (
                    "learning",
                    "practicing",
                    "needs_remediation",
                    "ready_for_checkpoint",
                )
            ),
            "not_started_count": counts["not_started"],
            "locked_count": counts["locked"],
            "current_topic": current,
            "recommended_topic_id": decision.get("recommended_topic_id"),
            "next_action": decision["next_action"],
            "reasons": decision["reasons"],
            "recent_practice": self.repository.list_recent_submissions(
                student_id,
                course=course,
                limit=5,
            ),
            "stages": [
                {"stage": stage, "title": title, "topics": stage_topics}
                for (stage, title), stage_topics in stages.items()
            ],
        }

    def evaluate_topic_gate(self, student_id: str, topic: dict[str, Any], state):
        state = state or {
            "mastery": 0.5,
            "evidence_count": 0,
            "checkpoint_count": 0,
            "latest_checkpoint_score": None,
        }
        return evaluate_mastery_gate(
            MasteryGateInput(
                mastery=float(state["mastery"]),
                valid_attempt_count=int(state["evidence_count"]),
                checkpoint_count=int(state["checkpoint_count"]),
                latest_checkpoint_score=(
                    float(state["latest_checkpoint_score"])
                    if state.get("latest_checkpoint_score") is not None
                    else None
                ),
                required_dimensions=frozenset(topic.get("required_dimensions") or []),
                checkpoint_dimensions=frozenset(
                    self.repository.get_latest_checkpoint_dimensions(
                        student_id,
                        topic["id"],
                    )
                ),
                unresolved_critical_misconception_count=(
                    self.repository.count_unresolved_critical_misconceptions(
                        student_id,
                        topic["id"],
                    )
                ),
                prerequisite_masteries=self.repository.get_prerequisite_masteries(
                    student_id,
                    topic["id"],
                ),
            ),
            MasteryGateConfig(
                mastery_threshold=self.settings.mastery_gate_threshold,
                prerequisite_mastery_threshold=self.settings.prerequisite_mastery_threshold,
                minimum_valid_attempts=self.settings.mastery_min_valid_attempts,
                checkpoint_score_threshold=self.settings.mastery_checkpoint_score,
                minimum_dimension_coverage=self.settings.mastery_min_dimension_coverage,
            ),
        )

    @staticmethod
    def _status(state) -> str:
        if state is not None and state["status"] == "mastered":
            return "mastered"
        return state["status"] if state is not None and state["status"] != "locked" else "not_started"

    @staticmethod
    def _current_topic(views: list[dict[str, Any]]) -> dict[str, Any] | None:
        for wanted in (
            "needs_remediation",
            "learning",
            "practicing",
            "ready_for_checkpoint",
            "not_started",
        ):
            match = next((item for item in views if item["status"] == wanted), None)
            if match is not None:
                return match
        return None
