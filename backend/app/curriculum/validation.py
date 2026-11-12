from collections.abc import Sequence

from app.curriculum.models import CurriculumSeed


class CurriculumValidationError(ValueError):
    pass


class TopicOwnershipError(CurriculumValidationError):
    pass


def validate_curriculum(seeds: Sequence[CurriculumSeed]) -> None:
    """Keep canonical topic identifiers unique across the supplied courses."""
    seen: set[str] = set()
    for seed in seeds:
        for topic in seed.topics:
            if topic.id in seen:
                raise CurriculumValidationError(f"知识点 ID {topic.id} 在多个课程中重复")
            seen.add(topic.id)
