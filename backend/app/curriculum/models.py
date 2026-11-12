from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.types import Course


class TopicSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=3)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    title: str = Field(min_length=1)
    stage: int = Field(ge=1)
    stage_title: str = Field(min_length=1)
    order_index: int = Field(ge=1)
    description: str = Field(min_length=1)
    learning_objectives: list[str] = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    retrieval_keywords: list[str] = Field(min_length=1)
    difficulty: str = Field(pattern=r"^(easy|medium|hard)$")
    required_dimensions: list[str] = Field(min_length=1)
    active: bool = True

    @model_validator(mode="after")
    def validate_unique_lists(self) -> "TopicSeed":
        for field_name in (
            "learning_objectives",
            "aliases",
            "retrieval_keywords",
            "required_dimensions",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{self.id}.{field_name} 不能包含重复项")
        return self


class CurriculumSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course: Course
    topics: list[TopicSeed] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_stable_identifiers(self) -> "CurriculumSeed":
        prefix = {Course.MACHINE_LEARNING: "ml.", Course.ADVANCED_MATHEMATICS: "math.",
                  Course.LINEAR_ALGEBRA: "la.", Course.PROBABILITY_STATISTICS: "prob."}.get(self.course, self.course.value + ".")
        allowed_dimensions = (
            {"concept", "mathematics", "mechanism", "engineering", "application"}
            if self.course is Course.MACHINE_LEARNING
            else {
                "concept",
                "theorem_condition",
                "derivation",
                "calculation",
                "application",
            }
        )
        ids = [topic.id for topic in self.topics]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.course.value} 存在重复知识点 ID")
        slugs = [topic.slug for topic in self.topics]
        if len(slugs) != len(set(slugs)):
            raise ValueError(f"{self.course.value} 存在重复 slug")
        orders = [topic.order_index for topic in self.topics]
        if len(orders) != len(set(orders)):
            raise ValueError(f"{self.course.value} 存在重复 order_index")
        invalid = [topic.id for topic in self.topics if not topic.id.startswith(prefix)]
        if invalid:
            raise ValueError(
                f"{self.course.value} 知识点 ID 前缀无效: {', '.join(invalid)}"
            )
        for topic in self.topics:
            unknown = set(topic.required_dimensions) - allowed_dimensions
            if unknown:
                raise ValueError(
                    f"{topic.id} 包含当前课程不支持的能力维度: "
                    f"{', '.join(sorted(unknown))}"
                )
        return self
