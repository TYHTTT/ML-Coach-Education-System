from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError
from app.core.types import Course

from app.curriculum.models import CurriculumSeed, PrerequisiteSeed
from app.curriculum.validation import CurriculumValidationError, validate_curriculum
from app.services.learning_repository import LearningRepository


SEED_DIRECTORY = Path(__file__).resolve().parent / "seeds"
DEFAULT_SEED_PATHS = (
    SEED_DIRECTORY / "machine_learning.json",
    SEED_DIRECTORY / "advanced_mathematics.json",
)


class CurriculumSeedError(ValueError):
    pass


def load_seed(path: str | Path) -> CurriculumSeed:
    seed_path = Path(path)
    try:
        data = json.loads(seed_path.read_text(encoding="utf-8"))
        return CurriculumSeed.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise CurriculumSeedError(f"课程 Seed 无效 ({seed_path.name}): {exc}") from exc


def seed_curriculum(
    repository: LearningRepository,
    seed_paths: Sequence[str | Path] | None = None,
    *,
    initialize_only: bool = False,
) -> dict[str, int]:
    if initialize_only:
        with repository._connect() as connection:
            existing = connection.execute("SELECT course,count(*) AS count FROM curriculum_topics GROUP BY course").fetchall()
        if existing:
            return {row["course"]: row["count"] for row in existing}
    seeds = [load_seed(path) for path in (seed_paths or DEFAULT_SEED_PATHS)]
    preparation_ids: list[str] = []
    if seed_paths is None:
        configuration = json.loads((SEED_DIRECTORY / "content_curriculum.json").read_text(encoding="utf-8"))
        by_course = {seed.course.value: seed for seed in seeds}
        for addition in configuration["additional_courses"]:
            extra = CurriculumSeed.model_validate(addition)
            if extra.course.value in by_course:
                existing = by_course[extra.course.value]
                by_course[extra.course.value] = existing.model_copy(update={"topics": existing.topics + extra.topics})
            else:
                by_course[extra.course.value] = extra
        seeds = list(by_course.values())
        for seed in seeds:
            for topic in seed.topics:
                if topic.id in configuration["relations"]:
                    topic.prerequisites = [PrerequisiteSeed.model_validate(edge) for edge in configuration["relations"][topic.id]]
        preparation_ids = configuration["math_preparation_topic_ids"]
    try:
        validate_curriculum(seeds)
    except CurriculumValidationError as exc:
        raise CurriculumSeedError(str(exc)) from exc

    repository.upsert_curriculum(seeds)
    if preparation_ids:
        with repository._connect() as connection:
            for index, topic_id in enumerate(preparation_ids, 1):
                topic = repository.require_topic(topic_id)
                connection.execute("""INSERT INTO topic_placements(course_id,topic_id,parent_group_id,group_title,order_index,is_reference)
                    VALUES ('machine_learning',?,?,?,?,1) ON CONFLICT(course_id,topic_id) DO UPDATE SET
                    parent_group_id=excluded.parent_group_id,group_title=excluded.group_title,order_index=excluded.order_index,is_reference=1""",
                    (topic_id,"math-preparation-" + topic["course"],"数学准备 · " + Course(topic["course"]).display_name,index))
    return {
        seed.course.value: len(seed.topics)
        for seed in seeds
    }
