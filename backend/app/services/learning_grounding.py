from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from app.core.types import Course
from app.services.dify import resource_snapshots


@dataclass(frozen=True, slots=True)
class GroundingResult:
    """Immutable source evidence returned by Dify for one learning operation."""

    query: str
    source_snapshot: list[dict[str, Any]]

    @property
    def source_ids(self) -> set[str]:
        return {str(item["source_id"]) for item in self.source_snapshot}

    @property
    def source_summary(self) -> list[dict[str, Any]]:
        return [
            {
                "source_id": item["source_id"],
                "source_file": item["source_file"],
                "title": item.get("title"),
            }
            for item in self.source_snapshot
        ]


class LearningGroundingService:
    """Request course evidence from Dify; no local indexing or retrieval."""

    def __init__(self, *, agent) -> None:
        self.agent = agent

    async def retrieve(
        self,
        *,
        course: Course,
        topic: Mapping[str, Any],
        purpose: str,
        user_question: str = "",
        error_tags: Iterable[str] = (),
        practice_goal: str = "",
        topic_ids: list[str] | None = None,
    ) -> GroundingResult:
        query = self.build_query(
            topic=topic,
            purpose=purpose,
            user_question=user_question,
            error_tags=error_tags,
            practice_goal=practice_goal,
        )
        if topic_ids == []:
            return GroundingResult(query=query, source_snapshot=[])
        result = await self.agent.run([
            {"role": "system", "content": f"请从 Dify 知识库检索{course.display_name}的课程原文，用于可靠出题。只使用指定课程和知识点的资料，保留真实引用；资料不足则说明。"},
            {"role": "user", "content": query},
        ], course=course, topic_id=str(topic["id"]))
        return GroundingResult(
            query=query,
            source_snapshot=resource_snapshots(result["resources"], course=course, topic_ids=topic_ids),
        )

    @staticmethod
    def build_query(
        *,
        topic: Mapping[str, Any],
        purpose: str,
        user_question: str = "",
        error_tags: Iterable[str] = (),
        practice_goal: str = "",
    ) -> str:
        def joined(value: Any) -> str:
            if isinstance(value, str):
                return value.strip()
            if isinstance(value, (list, tuple, set)):
                return "；".join(str(item).strip() for item in value if str(item).strip())
            return ""

        parts = [
            f"知识点：{str(topic.get('title', '')).strip()}",
            f"别名：{joined(topic.get('aliases', []))}",
            f"检索关键词：{joined(topic.get('retrieval_keywords', []))}",
            f"学习目标：{joined(topic.get('learning_objectives', []))}",
            f"检索用途：{purpose}",
        ]
        if user_question.strip():
            parts.append(f"学生当前问题：{user_question.strip()}")
        normalized_errors = joined(list(error_tags))
        if normalized_errors:
            parts.append(f"当前错误标签：{normalized_errors}")
        if practice_goal.strip():
            parts.append(f"当前练习目的：{practice_goal.strip()}")
        return "\n".join(part for part in parts if not part.endswith("："))
