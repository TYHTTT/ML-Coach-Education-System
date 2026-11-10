from __future__ import annotations

from typing import Protocol

from app.core.types import Course


class LLMClient(Protocol):
    async def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
    ) -> str:
        ...


def for_learning_task(client: LLMClient, course: Course, topic_id: str) -> LLMClient:
    """Bind remote application inputs for a task, including any JSON repairs."""
    bind = getattr(client, "for_task", None)
    return bind(course, topic_id) if bind else client
