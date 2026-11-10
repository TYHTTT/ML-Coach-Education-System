from __future__ import annotations

import json
import re
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.core.config import Settings
from app.core.exceptions import (
    EvaluationUncertainError,
    InvalidQuestionAnswerError,
    StructuredOutputInvalidError,
)
from app.core.types import Course
from app.prompts.learning import build_remediation_messages
from app.schemas.chat import SourceResponse
from app.schemas.practice import (
    PracticeQuestionInternal,
    PracticeSetInternal,
    referenced_internal_source_ids,
)
from app.schemas.practice_api import RemediationResponse
from app.services.learning_repository import LearningRepository
from app.services.llm.base import LLMClient, for_learning_task
from app.services.structured_output import generate_validated


class RemediationGeneration(BaseModel):
    """Strict private LLM contract used to build one remediation artifact."""

    model_config = ConfigDict(extra="forbid")

    diagnosis: str = Field(min_length=1, max_length=20_000)
    explanation: str = Field(min_length=1, max_length=40_000)
    contrast_example: str = Field(min_length=1, max_length=30_000)
    evidence_source_ids: list[str] = Field(min_length=1, max_length=100)
    targeted_question: PracticeQuestionInternal

    @field_validator("diagnosis", "explanation", "contrast_example")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("remediation text must not be empty")
        return normalized

    @field_validator("evidence_source_ids")
    @classmethod
    def unique_evidence(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized) or len(normalized) != len(set(normalized)):
            raise ValueError("evidence_source_ids must be unique and non-empty")
        return normalized

    @model_validator(mode="after")
    def validate_grounding(self, info: ValidationInfo) -> "RemediationGeneration":
        source_ids = set((info.context or {}).get("source_ids", set()))
        if not source_ids:
            raise ValueError("a real source snapshot is required")
        if not set(self.evidence_source_ids).issubset(source_ids):
            raise ValueError("remediation cites a source outside source_snapshot")
        if not set(self.targeted_question.source_ids).issubset(source_ids):
            raise ValueError("targeted question cites a source outside source_snapshot")
        leaked_source_ids = referenced_internal_source_ids(
            [
                self.targeted_question.question,
                *(item.text for item in self.targeted_question.options or []),
            ],
            source_ids,
        )
        if leaked_source_ids:
            raise ValueError(
                "student-visible question/options must not mention internal "
                "source_ids: " + ", ".join(leaked_source_ids)
            )
        # A one-question set cannot satisfy the product rule that a set must not
        # consist solely of multiple choice.  Targeted remediation also benefits
        # from requiring the student to produce an answer.
        if self.targeted_question.question_type == "multiple_choice":
            raise ValueError("the targeted remediation question cannot be multiple choice")
        original_question_hash = str(
            (info.context or {}).get("original_question_hash", "")
        )
        if (
            original_question_hash
            and self.targeted_question.normalized_question_hash == original_question_hash
        ):
            raise ValueError("the targeted remediation question must be new")
        return self


class RemediationService:
    """Generate focused remediation from the attempt's immutable evidence.

    This service deliberately performs no fresh retrieval.  The explanation,
    hidden answer key, rubric and targeted question are all constrained to the
    exact real-chunk snapshot saved when the original practice set was created.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        repository: LearningRepository,
        llm_client: LLMClient,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.llm_client = llm_client

    async def create(
        self,
        *,
        student_id: str,
        topic_id: str,
        attempt_id: str,
    ) -> RemediationResponse:
        self.repository.require_student(student_id)
        topic = self.repository.require_topic(topic_id, student_id=student_id)
        context = self.repository.get_attempt_context(
            attempt_id,
            student_id=student_id,
        )
        if context is None:
            raise InvalidQuestionAnswerError(message="未找到可用于补救的答题记录")
        if str(context.get("topic_id")) != topic_id:
            raise InvalidQuestionAnswerError(message="答题记录与当前知识点不匹配")
        stored_evaluation = context.get("evaluation")
        if not isinstance(stored_evaluation, dict):
            stored_evaluation = context
        if not bool(stored_evaluation.get("evaluation_reliable")):
            raise EvaluationUncertainError(
                message="原答题评价不可靠，无法据此生成补救内容；请先重新提交答案"
            )

        source_snapshot = self._dict_list(context.get("source_snapshot"))
        source_ids = {
            str(item.get("source_id", "")).strip()
            for item in source_snapshot
            if str(item.get("source_id", "")).strip()
        }
        if not source_snapshot or not source_ids:
            raise StructuredOutputInvalidError(
                message="原练习缺少可核验资料，无法生成可靠补救内容",
                internal_message=f"attempt {attempt_id} has no source snapshot",
            )

        misconception_tags = self._string_list(
            stored_evaluation.get("misconception_tags")
        )
        missing_points = self._string_list(stored_evaluation.get("missing_points"))
        if (
            not misconception_tags
            and not missing_points
            and float(stored_evaluation.get("score") or 0) >= 80
        ):
            raise InvalidQuestionAnswerError(message="该答题记录没有需要补救的错误")

        course = Course(str(context.get("course") or topic["course"]))
        stored_question = context.get("question")
        if not isinstance(stored_question, dict):
            stored_question = {
                "question_id": context.get("question_id"),
                "question_type": context.get("question_type"),
                "difficulty": context.get("difficulty"),
                "question": context.get("question_text") or context.get("question"),
                "dimensions": context.get("dimensions") or {},
                "source_ids": context.get("source_ids") or [],
            }
        question = {
            "question_id": stored_question.get("question_id"),
            "question_type": stored_question.get("question_type"),
            "difficulty": stored_question.get("difficulty"),
            "question": stored_question.get("question"),
            "dimensions": stored_question.get("dimensions") or {},
            "source_ids": stored_question.get("source_ids") or [],
        }
        evaluation = {
            "score": stored_evaluation.get("score"),
            "verdict": stored_evaluation.get("verdict"),
            "dimension_scores": stored_evaluation.get("dimension_scores") or {},
            "correct_points": stored_evaluation.get("correct_points") or [],
            "missing_points": missing_points,
            "misconception_tags": misconception_tags,
            "critical_misconception": bool(
                stored_evaluation.get("critical_misconception")
            ),
            "feedback": stored_evaluation.get("feedback") or "",
            "reference_answer": stored_evaluation.get("reference_answer") or "",
            "evidence_source_ids": stored_evaluation.get("evidence_source_ids") or [],
        }
        messages = build_remediation_messages(
            course=course,
            topic={
                "id": topic["id"],
                "title": topic["title"],
                "learning_objectives": topic.get("learning_objectives", []),
                "required_dimensions": topic.get("required_dimensions", []),
            },
            question=question,
            source_snapshot=source_snapshot,
            student_answer=str(context.get("student_answer") or context.get("answer_text") or ""),
            evaluation=evaluation,
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "只输出符合以下 JSON Schema 的对象。targeted_question 是一道新的专项小题；"
                    "不得是选择题，max_score 固定为 100，rubric 总分固定为 100。"
                    "targeted_question.question 和 options[].text 不得出现 S1、[S1] 等任何 "
                    "source_id；题目必须对学生自包含，证据编号只写入 source_ids。"
                    "其 answer_key 和 rubric 仅供后端保存，绝不能写进 diagnosis、explanation "
                    "或 contrast_example。\n"
                    + json.dumps(
                        RemediationGeneration.model_json_schema(),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                ),
            }
        )
        generated = await generate_validated(
            llm_client=for_learning_task(self.llm_client, course, topic["id"]),
            messages=messages,
            model=RemediationGeneration,
            temperature=self.settings.remediation_temperature,
            repair_attempts=self.settings.evaluation_max_repair_attempts,
            validation_context={
                "source_ids": source_ids,
                "original_question_hash": self._question_hash(
                    str(stored_question.get("question") or "")
                ),
            },
        )

        targeted_question = generated.targeted_question.model_copy(
            update={
                "question_id": str(uuid.uuid4()),
                "position": 1,
                "max_score": 100,
            }
        )
        practice_set = PracticeSetInternal(
            practice_set_id=str(uuid.uuid4()),
            course=course,
            topic_id=topic_id,
            kind="practice",
            required_dimensions=list(topic.get("required_dimensions") or []),
            questions=[targeted_question],
            source_snapshot=source_snapshot,
        )
        self.repository.create_practice_set(
            student_id=student_id,
            practice_set=practice_set,
            requested_difficulty=targeted_question.difficulty,
            target_misconception_tags=misconception_tags,
        )
        return RemediationResponse(
            topic_id=topic_id,
            diagnosis=generated.diagnosis,
            explanation=generated.explanation,
            contrast_example=generated.contrast_example,
            targeted_question_set_id=practice_set.practice_set_id,
            sources=self._public_sources(source_snapshot, generated.evidence_source_ids),
        )

    @staticmethod
    def _dict_list(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        result: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, BaseModel):
                result.append(item.model_dump())
            elif isinstance(item, dict):
                result.append(dict(item))
        return result

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, (list, tuple)):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _question_hash(question: str) -> str:
        from hashlib import sha256

        normalized = " ".join(question.casefold().split())
        return sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _public_sources(
        snapshot: list[dict[str, Any]],
        evidence_source_ids: list[str],
    ) -> list[SourceResponse]:
        by_id = {str(item["source_id"]): item for item in snapshot}
        sources: list[SourceResponse] = []
        for source_id in evidence_source_ids:
            item = by_id[source_id]
            snippet = re.sub(r"\s+", " ", str(item.get("content") or "")).strip()
            if len(snippet) > 260:
                snippet = snippet[:257].rstrip() + "..."
            sources.append(
                SourceResponse(
                    source_id=source_id,
                    document_id=str(item["document_id"]),
                    source_file=str(item["source_file"]),
                    title=item.get("title"),
                    chapter=item.get("chapter"),
                    section=item.get("section"),
                    page=item.get("page"),
                    chunk_index=int(item["chunk_index"]),
                    snippet=snippet,
                    distance=None,
                )
            )
        return sources
