from __future__ import annotations

import json
import math
import uuid
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.core.config import Settings
from app.core.exceptions import (
    InvalidQuestionAnswerError,
    KnowledgeInsufficientError,
    StructuredOutputInvalidError,
)
from app.core.types import Course
from app.prompts.learning import build_practice_generation_messages
from app.schemas.practice import (
    PracticeQuestionInternal,
    PracticeSetInternal,
    referenced_internal_source_ids,
)
from app.schemas.practice_api import CreatePracticeSetRequest, PracticeSetResponse
from app.services.learning_grounding import LearningGroundingService
from app.services.learning_repository import LearningRepository
from app.services.llm.base import LLMClient, for_learning_task
from app.services.structured_output import generate_validated, json_schema_instruction


ML_QUESTION_TYPES = {
    "concept_explanation",
    "mathematical_reasoning",
    "why_mechanism",
    "code_reading",
    "case_analysis",
    "multiple_choice",
    "numeric",
}
MATH_QUESTION_TYPES = {
    "concept_explanation",
    "theorem_condition",
    "calculation",
    "derivation",
    "proof_outline",
    "error_correction",
    "application",
    "multiple_choice",
    "numeric",
}
COURSE_DIMENSIONS = {
    Course.MACHINE_LEARNING: {
        "concept",
        "mathematics",
        "mechanism",
        "engineering",
        "application",
    },
    Course.ADVANCED_MATHEMATICS: {
        "concept",
        "theorem_condition",
        "derivation",
        "calculation",
        "application",
    },
}


class GeneratedPracticePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[PracticeQuestionInternal] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def unique_questions(self, info: ValidationInfo) -> "GeneratedPracticePayload":
        hashes = [question.normalized_question_hash for question in self.questions]
        if len(hashes) != len(set(hashes)):
            raise ValueError("generated questions must be unique")
        expected_count = (info.context or {}).get("expected_count")
        if expected_count is not None and len(self.questions) != int(expected_count):
            raise ValueError(
                "questions must contain exactly "
                f"{int(expected_count)} items (current count={len(self.questions)})"
            )
        source_ids = {
            str(item).strip()
            for item in (info.context or {}).get("source_ids", set())
            if str(item).strip()
        }
        leaked_source_ids = referenced_internal_source_ids(
            [
                text
                for question in self.questions
                for text in [
                    question.question,
                    *(item.text for item in question.options or []),
                ]
            ],
            source_ids,
        )
        if leaked_source_ids:
            raise ValueError(
                "student-visible question/options must not mention internal "
                "source_ids: " + ", ".join(leaked_source_ids)
            )
        return self


class KnowledgeInsufficientPayload(BaseModel):
    """The only accepted no-question response from the generation model."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["knowledge_insufficient"]
    message: str = Field(min_length=1, max_length=2_000)
    missing_topic: str = Field(min_length=1, max_length=500)

    @field_validator("message", "missing_topic")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("knowledge_insufficient fields must not be empty")
        return normalized


class PracticeGenerationEnvelope(
    RootModel[GeneratedPracticePayload | KnowledgeInsufficientPayload]
):
    """Strict union matching both branches promised by the generation prompt."""


class GeneratedPrerequisiteQuestion(PracticeQuestionInternal):
    tested_competencies: list[str] = Field(min_length=1)


class GeneratedPrerequisitePayload(GeneratedPracticePayload):
    questions: list[GeneratedPrerequisiteQuestion] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def registered_competencies(self, info: ValidationInfo):
        required = set((info.context or {}).get("required_competencies", []))
        covered = {c for q in self.questions for c in q.tested_competencies}
        if covered != required:
            raise ValueError("前置小测必须且只能覆盖已注册的 required_competencies")
        return self


class PrerequisiteGenerationEnvelope(
    RootModel[GeneratedPrerequisitePayload | KnowledgeInsufficientPayload]
):
    """A local verification records actual per-question competency coverage."""


def normalize_generated_rubric_totals(value: Any) -> Any:
    """Scale positive numeric rubric points to 100 without changing ratios.

    This is intentionally limited to untrusted LLM generation payloads.  The
    canonical ``PracticeQuestionInternal`` contract remains strict for every
    other caller and persistence path.
    """

    if not isinstance(value, dict) or not isinstance(value.get("questions"), list):
        return value
    normalized_payload = dict(value)
    normalized_questions: list[Any] = []
    for raw_question in value["questions"]:
        if not isinstance(raw_question, dict) or not isinstance(
            raw_question.get("rubric"), list
        ):
            normalized_questions.append(raw_question)
            continue
        rubric = raw_question["rubric"]
        points: list[float] = []
        valid = bool(rubric)
        for criterion in rubric:
            point = criterion.get("points") if isinstance(criterion, dict) else None
            if (
                isinstance(point, bool)
                or not isinstance(point, (int, float))
                or not math.isfinite(float(point))
                or float(point) <= 0
            ):
                valid = False
                break
            points.append(float(point))
        total = sum(points)
        if not valid or not math.isfinite(total) or total <= 0:
            normalized_questions.append(raw_question)
            continue
        if math.isclose(total, 100.0, abs_tol=1e-6):
            normalized_questions.append(raw_question)
            continue
        scaled = [point * 100.0 / total for point in points]
        if scaled:
            scaled[-1] = 100.0 - sum(scaled[:-1])
        if any(not math.isfinite(point) or point <= 0 or point > 100 for point in scaled):
            normalized_questions.append(raw_question)
            continue
        normalized_rubric = [
            {**criterion, "points": point}
            for criterion, point in zip(rubric, scaled, strict=True)
        ]
        normalized_questions.append(
            {**raw_question, "rubric": normalized_rubric}
        )
    normalized_payload["questions"] = normalized_questions
    return normalized_payload


class PracticeService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: LearningRepository,
        grounding: LearningGroundingService,
        llm_client: LLMClient,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.grounding = grounding
        self.llm_client = llm_client

    async def create_set(
        self,
        *,
        student_id: str,
        request: CreatePracticeSetRequest,
    ) -> PracticeSetResponse:
        self.repository.require_student(student_id)
        topic = self.repository.require_topic(request.topic_id, student_id=student_id)
        internal, grounding, _ = await self._prepare_set(
            student_id=student_id, request=request, topic=topic,
        )
        self.repository.create_practice_set(
            student_id=student_id,
            practice_set=internal,
            requested_difficulty=request.difficulty,
        )
        return PracticeSetResponse(
            practice_set_id=internal.practice_set_id,
            topic_id=internal.topic_id,
            mode=internal.kind,
            questions=internal.to_public().questions,
            source_summary=grounding.source_summary,
        )

    async def create_prerequisite_test(self, *, student_id: str, payload):
        from app.services.assessment_service import AssessmentService, RULE_VERSION

        assessment = AssessmentService(self.repository, self.settings)
        target, competencies = assessment.prerequisite_target(student_id, payload)
        topic = self.repository.require_topic(target["id"])
        scoped_topic = {
            **topic,
            "learning_objectives": [
                "仅验证当前后续知识点所需的局部前置能力，不检验整门课。",
                *competencies,
                str(target.get("reason") or ""),
            ],
        }
        request = CreatePracticeSetRequest(
            topic_id=topic["id"], mode="practice", count=payload.question_count,
        )
        internal, _, generated = await self._prepare_set(
            student_id=student_id, request=request, topic=scoped_topic,
            required_competencies=competencies,
        )
        internal = internal.model_copy(update={"assessment_purpose": "prerequisite_test"})
        # Metadata and questions commit together; a crash cannot leave a local
        # verification misclassified as an ordinary mastery-bearing practice.
        with self.repository._connect() as connection:
            self.repository.create_practice_set(
                student_id=student_id, practice_set=internal, _connection=connection,
            )
            connection.execute(
                "UPDATE practice_sets SET purpose='prerequisite_test',prerequisite_for=?,rule_version=?,required_dimensions_snapshot_json=? WHERE id=?",
                (payload.topic_id, target.get("rule_version") or RULE_VERSION,
                 json.dumps(internal.required_dimensions), internal.practice_set_id),
            )
            for question, generated_question in zip(internal.questions, generated.questions, strict=True):
                # Per-set identity supports the exposure/first-attempt guard.
                identity = "dynamic." + question.question_id
                connection.execute(
                    "UPDATE practice_questions SET family_id=?,topic_ids_json=?,competencies_json=? WHERE id=?",
                    (identity, json.dumps([topic["id"]]),
                     json.dumps(generated_question.tested_competencies), question.question_id),
                )
        return assessment.get(student_id, internal.practice_set_id)

    async def _prepare_set(
        self, *, student_id: str, request: CreatePracticeSetRequest,
        topic: dict[str, Any], required_competencies: list[str] | None = None,
    ):
        course = Course(topic["course"])
        count = request.count or (
            self.settings.practice_default_count
            if request.mode == "practice"
            else self.settings.checkpoint_default_count
        )
        if count > self.settings.practice_max_count:
            raise InvalidQuestionAnswerError(
                message=f"练习题数量不能超过 {self.settings.practice_max_count} 道"
            )

        weak_dimensions = self._weak_dimensions(student_id, topic)
        recent_questions = self.repository.list_recent_question_texts(
            student_id,
            request.topic_id,
            limit=self.settings.recent_question_dedup_count,
        )
        grounding = await self.grounding.retrieve(
            course=course,
            topic=topic,
            purpose="prerequisite_test" if required_competencies else "practice_generation",
            **({"topic_ids": [str(topic["id"])]} if required_competencies else {}),
            practice_goal=(
                "只验证这些局部能力：" + "；".join(required_competencies)
                if required_competencies else "知识点综合验收并覆盖必需能力维度"
                if request.mode == "checkpoint"
                else "针对当前薄弱维度进行主动练习"
            ),
        )
        if not grounding.source_snapshot:
            raise KnowledgeInsufficientError(
                message=(
                    "Dify 未返回足够的可引用课程资料，暂时无法生成可靠练习，请检查 Dify 知识检索与引用配置。"
                ),
                internal_message=f"no grounded sources for {request.topic_id}",
            )

        previous_hashes = self.repository.list_recent_question_hashes(
            student_id,
            request.topic_id,
            limit=self.settings.recent_question_dedup_count,
        )
        internal: PracticeSetInternal | None = None
        last_error: Exception | None = None
        for _ in range(self.settings.question_generation_max_retries + 1):
            try:
                generated = await self._generate(
                    course=course,
                    topic=topic,
                    source_snapshot=grounding.source_snapshot,
                    mode=request.mode,
                    count=count,
                    requested_difficulty=request.difficulty,
                    weak_dimensions=weak_dimensions,
                    recent_questions=recent_questions,
                    required_competencies=required_competencies,
                )
                internal = self._finalize_generated_set(
                    generated=generated,
                    course=course,
                    topic=topic,
                    mode=request.mode,
                    expected_count=count,
                    source_snapshot=grounding.source_snapshot,
                    previous_hashes=previous_hashes,
                )
                break
            except (ValidationError, ValueError, StructuredOutputInvalidError) as exc:
                last_error = exc
        if internal is None:
            raise StructuredOutputInvalidError(
                internal_message=f"practice generation failed: {type(last_error).__name__}"
            )

        return internal, grounding, generated

    def get_set(self, *, student_id: str, practice_set_id: str) -> PracticeSetResponse:
        self.repository.require_student(student_id)
        internal = self.repository.get_practice_set_internal(
            practice_set_id,
            student_id=student_id,
        )
        snapshot = [item.model_dump() for item in internal.source_snapshot]
        summary = [
            {
                "source_id": item["source_id"],
                "source_file": item["source_file"],
                "title": item.get("title"),
            }
            for item in snapshot
        ]
        return PracticeSetResponse(
            practice_set_id=internal.practice_set_id,
            topic_id=internal.topic_id,
            mode=internal.kind,
            status=self.repository.get_practice_set_status(practice_set_id),
            questions=internal.to_public().questions,
            source_summary=summary,
        )

    async def _generate(
        self,
        *,
        course: Course,
        topic: dict[str, Any],
        source_snapshot: list[dict[str, Any]],
        mode: str,
        count: int,
        requested_difficulty: str,
        weak_dimensions: list[str],
        recent_questions: list[str],
        required_competencies: list[str] | None = None,
    ) -> GeneratedPracticePayload:
        messages = build_practice_generation_messages(
            course=course,
            topic={
                **self._prompt_topic(topic),
                "requested_difficulty": requested_difficulty,
            },
            source_snapshot=source_snapshot,
            kind=mode,  # type: ignore[arg-type]
            count=count,
            weak_dimensions=weak_dimensions,
            recent_questions=recent_questions,
        )
        envelope_model = PrerequisiteGenerationEnvelope if required_competencies else PracticeGenerationEnvelope
        if required_competencies:
            messages.append({"role": "user", "content": (
                "本次是局部前置小测，不是整课考试。每道题需明确填写实际检测的 tested_competencies，"
                "只能从以下列表选择，整套必须覆盖全部列表；不要仅贴标签，题目必须实际检验对应能力："
                + json.dumps(required_competencies, ensure_ascii=False)
            )})
        messages.append(
            json_schema_instruction(
                envelope_model,
                additional_rules=(
                    f"资料充分时 questions 必须恰好包含 {count} 道题；question_id 可暂用 "
                    "q1、q2，position 从 1 开始，max_score 固定为 100；每道题的 "
                    "rubric points 总和必须恰好为 100。question 和 options[].text "
                    "不得出现 S1、[S1] 等任何 source_id；题目必须自包含，证据编号只写入 "
                    "source_ids。资料不足时只能输出 "
                    '{"status":"knowledge_insufficient","message":"...",'
                    '"missing_topic":"..."}，不得同时输出 questions。'
                ),
            )
        )
        envelope = await generate_validated(
            llm_client=for_learning_task(self.llm_client, course, topic["id"]),
            messages=messages,
            model=envelope_model,
            temperature=self.settings.practice_generation_temperature,
            repair_attempts=self.settings.evaluation_max_repair_attempts,
            validation_context={
                "expected_count": count,
                "required_competencies": required_competencies or [],
                "source_ids": {
                    str(item.get("source_id", "")).strip()
                    for item in source_snapshot
                    if str(item.get("source_id", "")).strip()
                },
            },
            preprocess=normalize_generated_rubric_totals,
        )
        if isinstance(envelope.root, KnowledgeInsufficientPayload):
            raise KnowledgeInsufficientError(
                message=(
                    "Dify 未返回足够的可引用课程资料，暂时无法生成可靠练习，请检查 Dify 知识检索与引用配置。"
                ),
                internal_message=(
                    "generation model reported knowledge_insufficient for "
                    f"{topic.get('id')}: {envelope.root.missing_topic[:200]}"
                ),
            )
        return envelope.root

    def _finalize_generated_set(
        self,
        *,
        generated: GeneratedPracticePayload,
        course: Course,
        topic: dict[str, Any],
        mode: str,
        expected_count: int,
        source_snapshot: list[dict[str, Any]],
        previous_hashes: set[str],
    ) -> PracticeSetInternal:
        if len(generated.questions) != expected_count:
            raise ValueError("模型生成的题目数量不符合请求")
        allowed_types = (
            ML_QUESTION_TYPES
            if course is Course.MACHINE_LEARNING
            else MATH_QUESTION_TYPES
        )
        allowed_dimensions = COURSE_DIMENSIONS.get(course, COURSE_DIMENSIONS[Course.ADVANCED_MATHEMATICS])
        finalized: list[PracticeQuestionInternal] = []
        for position, question in enumerate(generated.questions, 1):
            if question.question_type not in allowed_types:
                raise ValueError("题型与课程不匹配")
            if not set(question.dimensions).issubset(allowed_dimensions):
                raise ValueError("能力维度与课程不匹配")
            normalized = question.model_copy(
                update={
                    "question_id": str(uuid.uuid4()),
                    "position": position,
                    "max_score": 100,
                }
            )
            if normalized.normalized_question_hash in previous_hashes:
                raise ValueError("生成题目与近期题目重复")
            finalized.append(normalized)
        if all(item.question_type == "multiple_choice" for item in finalized):
            raise ValueError("练习不能全部是选择题")
        if mode == "checkpoint":
            required = set(topic.get("required_dimensions") or [])
            covered = {dimension for item in finalized for dimension in item.dimensions}
            minimum = min(self.settings.mastery_min_dimension_coverage, len(required))
            if len(covered & required) < minimum:
                raise ValueError("checkpoint 未覆盖足够的 required_dimensions")
        return PracticeSetInternal(
            practice_set_id=str(uuid.uuid4()),
            course=course,
            topic_id=str(topic["id"]),
            kind=mode,  # type: ignore[arg-type]
            required_dimensions=list(topic.get("required_dimensions") or []),
            questions=finalized,
            source_snapshot=source_snapshot,
        )

    def _weak_dimensions(self, student_id: str, topic: dict[str, Any]) -> list[str]:
        states = {
            item["dimension"]: item
            for item in self.repository.list_dimension_states(student_id, topic["id"])
        }
        required = list(topic.get("required_dimensions") or [])
        return sorted(
            required,
            key=lambda dimension: (
                float(states.get(dimension, {}).get("mastery", 0.5)),
                dimension,
            ),
        )

    @staticmethod
    def _prompt_topic(topic: dict[str, Any]) -> dict[str, Any]:
        return {
            key: topic.get(key)
            for key in (
                "id",
                "course",
                "title",
                "description",
                "learning_objectives",
                "required_dimensions",
                "difficulty",
            )
        }
