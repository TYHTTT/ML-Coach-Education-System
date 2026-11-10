from __future__ import annotations

import json
import math
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.config import Settings
from app.core.exceptions import (
    DuplicateSubmissionError,
    InvalidQuestionAnswerError,
    PracticeSetAlreadySubmittedError,
    StructuredOutputInvalidError,
)
from app.core.types import Course
from app.learning.gate import MasteryGateConfig, MasteryGateInput, evaluate_mastery_gate
from app.learning.mastery import BetaEvidenceState, update_beta_evidence
from app.learning.misconceptions import normalize_misconception_tags
from app.prompts.learning import build_evaluation_messages
from app.schemas.learning import EvaluationResultInternal, MasteryUpdateEligibility
from app.schemas.practice import PracticeQuestionInternal, PracticeSetInternal
from app.schemas.practice_api import (
    PracticeSubmitResponse,
    QuestionEvaluationResponse,
    SubmitPracticeSetRequest,
)
from app.services.learning_repository import LearningRepository
from app.services.llm.base import LLMClient, for_learning_task
from app.services.structured_output import generate_validated, json_schema_instruction


def normalize_choice(value: str) -> str:
    normalized = re.sub(r"\s+", "", value or "").strip().upper()
    normalized = normalized.removeprefix("选项")
    if normalized.startswith(("A.", "B.", "C.", "D.", "E.", "F.")):
        normalized = normalized[0]
    return normalized


def score_multiple_choice(student_answer: str, correct_option: str) -> tuple[float, bool]:
    student = normalize_choice(student_answer)
    correct = normalize_choice(correct_option)
    if not student or not correct:
        return 0.0, False
    passed = student == correct
    return (100.0 if passed else 0.0), True


def parse_numeric_answer(value: str) -> float | None:
    text = (value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        number = float(Decimal(text))
    except (InvalidOperation, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def score_numeric(
    student_answer: str,
    numeric_answer: float,
    tolerance: float,
    accepted_units: list[str] | None = None,
) -> tuple[float, bool]:
    for unit in sorted(accepted_units or [], key=len, reverse=True):
        if unit and student_answer.strip().endswith(unit):
            student_answer = student_answer.strip()[:-len(unit)].strip()
            break
    parsed = parse_numeric_answer(student_answer)
    if parsed is None or not math.isfinite(numeric_answer) or not math.isfinite(tolerance) or tolerance < 0:
        return 0.0, False
    passed = abs(parsed - numeric_answer) <= tolerance
    return (100.0 if passed else 0.0), True


class EvaluationService:
    """Evaluate a saved set against its immutable answer/rubric/source snapshot."""

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

    async def submit(
        self,
        *,
        student_id: str,
        practice_set_id: str,
        request: SubmitPracticeSetRequest,
    ) -> PracticeSubmitResponse:
        self.repository.require_student(student_id)
        client_submission_id = str(request.client_submission_id)
        existing = self.repository.get_submission_by_client_id(
            client_submission_id,
            student_id=student_id,
            practice_set_id=practice_set_id,
        )
        if existing is not None:
            if existing.get("response_json"):
                response = PracticeSubmitResponse.model_validate_json(existing["response_json"])
                from app.services.assessment_service import AssessmentService
                AssessmentService(self.repository, self.settings).after_submit(student_id, practice_set_id, response)
                return response.model_copy(update={"idempotent_replay": True})
            raise DuplicateSubmissionError()

        practice_set = self.repository.get_practice_set_internal(
            practice_set_id,
            student_id=student_id,
        )
        if self.repository.get_practice_set_status(practice_set_id) == "submitted":
            raise PracticeSetAlreadySubmittedError()
        answers = {item.question_id: item.answer for item in request.answers}
        expected = {item.question_id for item in practice_set.questions}
        if set(answers) != expected:
            raise InvalidQuestionAnswerError(
                message="必须为练习集合中的每一道题提交且只提交一个答案"
            )

        topic = self.repository.require_topic(practice_set.topic_id)
        state_before = self.repository.ensure_topic_state(student_id, practice_set.topic_id)
        mastery_before = float(state_before["mastery"])
        submission_id = self.repository.reserve_submission(
            practice_set_id=practice_set_id,
            student_id=student_id,
            client_submission_id=client_submission_id,
            mastery_before=mastery_before,
        )

        evaluations: list[EvaluationResultInternal] = []
        for question in practice_set.questions:
            evaluations.append(
                await self._evaluate_question(
                    course=practice_set.course,
                    topic=topic,
                    question=question,
                    source_snapshot=[item.model_dump() for item in practice_set.source_snapshot],
                    student_answer=answers[question.question_id],
                )
            )
        attempt_ids = {
            question.question_id: str(uuid.uuid4())
            for question in practice_set.questions
        }

        eligible = [
            MasteryUpdateEligibility(
                evaluation_reliable=item.evaluation_reliable,
                evaluator_confidence=item.evaluator_confidence,
                minimum_confidence=self.settings.evaluator_min_confidence,
                question_valid=True,
                duplicate_submission=False,
                schema_valid=True,
            ).eligible
            for item in evaluations
        ]
        all_reliable = all(eligible)
        from app.services.assessment_service import evidence_allowed, AssessmentService
        can_apply = all_reliable and evidence_allowed(self.repository, practice_set_id)
        total_score = sum(item.score for item in evaluations) / len(evaluations)
        topic_changes: dict[str, Any] = {}
        dimension_changes: dict[str, dict[str, Any]] = {}
        state_after = dict(state_before)
        if can_apply:
            state_after, topic_changes, dimension_changes = self._calculate_mastery_updates(
                student_id=student_id,
                practice_set=practice_set,
                evaluations=evaluations,
                state_before=state_before,
                total_score=total_score,
            )

        gate = self._gate(
            student_id=student_id,
            practice_set=practice_set,
            topic=topic,
            state=state_after,
            evaluations=evaluations if can_apply else [],
        )
        if can_apply:
            now = self.repository._now()
            if gate.passed:
                topic_changes.update(status="mastered", mastered_at=now)
                state_after.update(status="mastered", mastered_at=now)
            elif any(item.critical_misconception for item in evaluations):
                topic_changes["status"] = "needs_remediation"
                state_after["status"] = "needs_remediation"
            elif gate.next_action == "take_checkpoint":
                topic_changes["status"] = "ready_for_checkpoint"
                state_after["status"] = "ready_for_checkpoint"
            else:
                topic_changes["status"] = "practicing"
                state_after["status"] = "practicing"

        status = "evaluated" if all_reliable else "evaluation_uncertain"
        public_evaluations = [
            self._public_evaluation(
                question=question,
                attempt_id=attempt_ids[question.question_id],
                result=result,
                source_snapshot=practice_set.source_snapshot,
            )
            for question, result in zip(practice_set.questions, evaluations, strict=True)
        ]
        reasons = self._gate_reasons(gate)
        if all_reliable and not can_apply:
            reasons = ["本次为局部前置验证，或题目已曝光/使用提示；保留分数反馈，不重复累计知识点掌握证据。"]
        response = PracticeSubmitResponse(
            practice_set_id=practice_set_id,
            submission_id=submission_id,
            status=status,
            total_score=total_score,
            mastery_before=mastery_before,
            mastery_after=float(state_after["mastery"]) if can_apply else mastery_before,
            evaluations=public_evaluations,
            gate=gate,
            next_action=gate.next_action if all_reliable else "practice",
            reasons=(
                reasons
                if all_reliable
                else ["本次评价结果不可靠，掌握度没有更新；请重新提交或生成练习"]
            ),
        )
        self.repository.finalize_submission(
            submission_id=submission_id,
            practice_set=practice_set,
            answers=answers,
            evaluations=evaluations,
            attempt_ids=attempt_ids,
            total_score=total_score,
            evaluation_status=status,
            mastery_before=mastery_before,
            mastery_after=response.mastery_after,
            gate_result=gate.model_dump(),
            response_json=response.model_dump_json(),
            topic_changes=topic_changes if all_reliable else {},
            dimension_changes=dimension_changes if all_reliable else {},
            mark_submitted=all_reliable,
            allow_evidence=can_apply,
        )
        AssessmentService(self.repository, self.settings).after_submit(student_id, practice_set_id, response)
        return response

    async def _evaluate_question(
        self,
        *,
        course: Course,
        topic: dict[str, Any],
        question: PracticeQuestionInternal,
        source_snapshot: list[dict[str, Any]],
        student_answer: str,
    ) -> EvaluationResultInternal:
        if question.question_type == "multiple_choice":
            score, valid = score_multiple_choice(
                student_answer,
                question.answer_key.correct_option or "",
            )
            return self._deterministic_result(question, score, valid, course)
        if question.question_type == "numeric":
            score, valid = score_numeric(
                student_answer,
                float(question.answer_key.numeric_answer or 0),
                float(question.answer_key.tolerance or 0),
                question.answer_key.accepted_units,
            )
            return self._deterministic_result(question, score, valid, course)

        messages = build_evaluation_messages(
            course=course,
            topic={
                "id": topic["id"],
                "title": topic["title"],
                "learning_objectives": topic.get("learning_objectives", []),
            },
            question={
                "question_id": question.question_id,
                "question_type": question.question_type,
                "difficulty": question.difficulty,
                "question": question.question,
                "dimensions": question.dimensions,
            },
            answer_key=question.answer_key.model_dump(),
            rubric=[item.model_dump() for item in question.rubric],
            source_snapshot=source_snapshot,
            student_answer=student_answer,
        )
        messages.append(
            json_schema_instruction(
                EvaluationResultInternal,
                additional_rules=(
                    "dimension_scores 的键只能来自本题维度："
                    + ", ".join(question.dimensions)
                    + "。evidence_source_ids 的值只能来自："
                    + ", ".join(question.source_ids)
                    + "。verdict=evaluation_uncertain 时 evaluation_reliable 必须为 false，"
                    "且 critical_misconception 必须为 false；其他 verdict 的 "
                    "evaluation_reliable 必须为 true。"
                ),
            )
        )
        try:
            result = await generate_validated(
                llm_client=for_learning_task(self.llm_client, course, topic["id"]),
                messages=messages,
                model=EvaluationResultInternal,
                temperature=self.settings.evaluation_temperature,
                repair_attempts=self.settings.evaluation_max_repair_attempts,
                validation_context={"source_ids": set(question.source_ids)},
            )
            if not set(result.dimension_scores).issubset(question.dimensions):
                raise ValueError("evaluator returned a dimension not assessed by the question")
            normalized_tags = normalize_misconception_tags(course, result.misconception_tags)
            result = result.model_copy(update={"misconception_tags": normalized_tags})
            if result.evaluator_confidence < self.settings.evaluator_min_confidence:
                return self._uncertain_result(question, "评价置信度不足")
            return result
        except Exception as exc:
            # Evaluation failure is a safe, retryable learning outcome.  It must
            # never mutate mastery or invent a diagnosis.
            return self._uncertain_result(
                question,
                f"评价结果无法可靠校验（{type(exc).__name__}）",
            )

    @staticmethod
    def _deterministic_result(
        question: PracticeQuestionInternal,
        score: float,
        valid: bool,
        course: Course,
    ) -> EvaluationResultInternal:
        if not valid:
            return EvaluationService._uncertain_result(question, "答案格式无法解析")
        correct = score >= 100
        tags = [] if correct else normalize_misconception_tags(course, ["other"])
        return EvaluationResultInternal(
            score=score,
            verdict="correct" if correct else "incorrect",
            dimension_scores={dimension: score for dimension in question.dimensions},
            correct_points=["答案与标准结果一致"] if correct else [],
            missing_points=[] if correct else ["答案与标准结果不一致"],
            misconception_tags=tags,
            critical_misconception=False,
            feedback="回答正确。" if correct else "答案不正确，请核对条件与计算过程。",
            reference_answer=question.answer_key.canonical_answer,
            evidence_source_ids=question.source_ids,
            evaluator_confidence=1.0,
            evaluation_reliable=True,
        )

    @staticmethod
    def _uncertain_result(
        question: PracticeQuestionInternal,
        feedback: str,
    ) -> EvaluationResultInternal:
        return EvaluationResultInternal(
            score=0,
            verdict="evaluation_uncertain",
            dimension_scores={},
            correct_points=[],
            missing_points=[],
            misconception_tags=[],
            critical_misconception=False,
            feedback=feedback,
            reference_answer=question.answer_key.canonical_answer,
            evidence_source_ids=question.source_ids,
            evaluator_confidence=0,
            evaluation_reliable=False,
        )

    def _calculate_mastery_updates(
        self,
        *,
        student_id: str,
        practice_set: PracticeSetInternal,
        evaluations: list[EvaluationResultInternal],
        state_before: dict[str, Any],
        total_score: float,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
        alpha = float(state_before["alpha"])
        beta = float(state_before["beta"])
        dimension_states = {
            item["dimension"]: item
            for item in self.repository.list_dimension_states(
                student_id,
                practice_set.topic_id,
            )
        }
        dimension_changes: dict[str, dict[str, Any]] = {}
        checkpoint = practice_set.kind == "checkpoint"
        for question, evaluation in zip(
            practice_set.questions,
            evaluations,
            strict=True,
        ):
            updated = update_beta_evidence(
                alpha,
                beta,
                evaluation.score,
                question.difficulty,
                checkpoint=checkpoint,
                confidence_target=self.settings.mastery_evidence_confidence_target,
            )
            alpha, beta = updated.alpha, updated.beta
            for dimension, score in evaluation.dimension_scores.items():
                current = dimension_changes.get(dimension) or dimension_states.get(dimension) or {
                    "alpha": 1.0,
                    "beta": 1.0,
                    "evidence_count": 0,
                }
                dimension_update = update_beta_evidence(
                    float(current["alpha"]),
                    float(current["beta"]),
                    score,
                    question.difficulty,
                    checkpoint=checkpoint,
                    confidence_target=self.settings.mastery_evidence_confidence_target,
                )
                dimension_changes[dimension] = {
                    "alpha": dimension_update.alpha,
                    "beta": dimension_update.beta,
                    "mastery": dimension_update.mastery,
                    "confidence": dimension_update.confidence,
                    "evidence_count": int(current.get("evidence_count", 0)) + 1,
                }
        state_after = dict(state_before)
        state_after.update(
            alpha=alpha,
            beta=beta,
            mastery=alpha / (alpha + beta),
            confidence=min(
                1.0,
                (alpha + beta - 2) / self.settings.mastery_evidence_confidence_target,
            ),
            evidence_count=int(state_before["evidence_count"]) + len(evaluations),
            attempt_count=int(state_before["attempt_count"]) + len(evaluations),
            practice_set_count=int(state_before["practice_set_count"])
            + (1 if not checkpoint else 0),
            checkpoint_count=int(state_before["checkpoint_count"])
            + (1 if checkpoint else 0),
            latest_score=total_score,
            best_score=max(float(state_before.get("best_score") or 0), total_score),
            latest_checkpoint_score=(
                total_score
                if checkpoint
                else state_before.get("latest_checkpoint_score")
            ),
            last_practiced_at=self.repository._now(),
        )
        topic_changes = {
            key: state_after[key]
            for key in (
                "alpha",
                "beta",
                "mastery",
                "confidence",
                "evidence_count",
                "attempt_count",
                "practice_set_count",
                "checkpoint_count",
                "latest_score",
                "best_score",
                "latest_checkpoint_score",
                "last_practiced_at",
            )
        }
        return state_after, topic_changes, dimension_changes

    def _gate(
        self,
        *,
        student_id: str,
        practice_set: PracticeSetInternal,
        topic: dict[str, Any],
        state: dict[str, Any],
        evaluations: list[EvaluationResultInternal],
    ):
        current_checkpoint_dimensions = (
            frozenset(
                dimension
                for item in evaluations
                for dimension in item.dimension_scores
            )
            if practice_set.kind == "checkpoint" and evaluations
            else frozenset(
                self.repository.get_latest_checkpoint_dimensions(
                    student_id,
                    practice_set.topic_id,
                )
            )
        )
        critical_count = self.repository.count_unresolved_critical_misconceptions(
            student_id,
            practice_set.topic_id,
        ) + sum(item.critical_misconception for item in evaluations)
        prerequisite_masteries = self.repository.get_prerequisite_masteries(
            student_id,
            practice_set.topic_id,
        )
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
                checkpoint_dimensions=current_checkpoint_dimensions,
                unresolved_critical_misconception_count=critical_count,
                prerequisite_masteries=prerequisite_masteries,
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
    def _public_evaluation(
        *,
        question: PracticeQuestionInternal,
        attempt_id: str,
        result: EvaluationResultInternal,
        source_snapshot,
    ) -> QuestionEvaluationResponse:
        by_id = {item.source_id: item for item in source_snapshot}
        sources = []
        for source_id in result.evidence_source_ids:
            source = by_id[source_id]
            snippet = re.sub(r"\s+", " ", source.content).strip()
            if len(snippet) > 260:
                snippet = snippet[:257].rstrip() + "..."
            sources.append(
                {
                    "source_id": source.source_id,
                    "source_course": source.source_course,
                    "topic_id": source.topic_id,
                    "document_id": source.document_id,
                    "source_file": source.source_file,
                    "title": source.title,
                    "chapter": source.chapter,
                    "section": source.section,
                    "page": source.page,
                    "chunk_index": source.chunk_index,
                    "snippet": snippet,
                    "distance": None,
                }
            )
        public = result.to_public().model_dump()
        public.pop("evidence_source_ids", None)
        return QuestionEvaluationResponse(
            question_id=question.question_id,
            attempt_id=attempt_id,
            sources=sources,
            **public,
        )

    @staticmethod
    def _gate_reasons(gate) -> list[str]:
        reasons: list[str] = []
        for name, requirement in gate.requirements:
            if requirement.passed:
                continue
            reasons.append(
                f"{name}: 当前 {requirement.current}，要求 {requirement.required}"
            )
        return reasons or ["已满足当前知识点的 Mastery Gate"]
