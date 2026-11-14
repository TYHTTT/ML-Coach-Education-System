from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from app.curriculum.models import CurriculumSeed
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
) -> dict[str, int]:
    seeds = [load_seed(path) for path in (seed_paths or DEFAULT_SEED_PATHS)]
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
    try:
        validate_curriculum(seeds)
    except CurriculumValidationError as exc:
        raise CurriculumSeedError(str(exc)) from exc

    repository.upsert_curriculum(seeds)
    return {
        seed.course.value: len(seed.topics)
        for seed in seeds
    }
