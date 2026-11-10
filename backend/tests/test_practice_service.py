from __future__ import annotations

import json

import pytest

from app.core.config import Settings
from app.core.exceptions import KnowledgeInsufficientError, StructuredOutputInvalidError
from app.core.types import Course
from app.services.learning_grounding import GroundingResult
from app.services.practice_service import PracticeService
from app.schemas.practice_api import CreatePracticeSetRequest


SOURCE = {
    "source_id": "S1",
    "document_id": "doc-1",
    "source_file": "logistic.md",
    "content": "逻辑回归使用伯努利似然，负对数似然等价于交叉熵。",
    "title": "逻辑回归",
    "chapter": "分类",
    "section": "参数估计",
    "page": None,
    "chunk_index": 1,
}


class FakeRepository:
    def __init__(self) -> None:
        self.saved = None

    def require_student(self, student_id, **kwargs):
        return {"id": student_id}

    def require_topic(self, topic_id, **kwargs):
        return {
            "id": topic_id,
            "course": Course.MACHINE_LEARNING.value,
            "title": "逻辑回归",
            "description": "二分类模型",
            "learning_objectives": ["解释交叉熵"],
            "aliases": [],
            "retrieval_keywords": ["伯努利似然"],
            "required_dimensions": ["concept", "mathematics", "mechanism"],
            "difficulty": "medium",
        }

    def list_dimension_states(self, student_id, topic_id):
        return []

    def list_recent_question_texts(self, *args, **kwargs):
        return []

    def list_recent_question_hashes(self, *args, **kwargs):
        return set()

    def create_practice_set(self, **kwargs):
        self.saved = kwargs["practice_set"]


class FakeGrounding:
    def __init__(self, sources):
        self.sources = sources

    async def retrieve(self, **kwargs):
        return GroundingResult(
            query="逻辑回归",
            source_snapshot=self.sources,
        )


class OneQuestionLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, messages, temperature=None):
        self.calls += 1
        return json.dumps(
            {
                "questions": [
                    {
                        "question_id": "q1",
                        "question_type": "concept_explanation",
                        "difficulty": "medium",
                        "question": "交叉熵为什么适合逻辑回归？",
                        "dimensions": {"concept": 1.0},
                        "options": None,
                        "answer_key": {
                            "canonical_answer": "它等价于伯努利负对数似然。",
                            "key_points": ["伯努利似然", "负对数似然"],
                            "accepted_variants": [],
                            "numeric_answer": None,
                            "tolerance": None,
                            "correct_option": None,
                        },
                        "rubric": [{"criterion": "说明似然关系", "points": 100}],
                        "source_ids": ["S1"],
                        "position": 1,
                        "max_score": 100,
                    }
                ]
            },
            ensure_ascii=False,
        )


class SequenceLLM:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls: list[list[dict[str, str]]] = []

    async def generate(self, messages, temperature=None):
        self.calls.append(messages)
        return json.dumps(self.payloads.pop(0), ensure_ascii=False)


def generated_question(
    *,
    question_id: str,
    question: str,
    rubric: list[dict] | None = None,
) -> dict:
    return {
        "question_id": question_id,
        "question_type": "concept_explanation",
        "difficulty": "medium",
        "question": question,
        "dimensions": {"concept": 1.0},
        "options": None,
        "answer_key": {
            "canonical_answer": "它等价于伯努利负对数似然。",
            "key_points": ["伯努利似然", "负对数似然"],
            "accepted_variants": [],
            "numeric_answer": None,
            "tolerance": None,
            "correct_option": None,
        },
        "rubric": rubric or [{"criterion": "说明似然关系", "points": 100}],
        "source_ids": ["S1"],
        "position": 1,
        "max_score": 100,
    }


def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        upload_path=tmp_path / "uploads",
    )


@pytest.mark.asyncio
async def test_practice_generation_persists_internal_but_returns_no_answer(tmp_path) -> None:
    repository = FakeRepository()
    llm = OneQuestionLLM()
    service = PracticeService(
        settings=settings(tmp_path),
        repository=repository,  # type: ignore[arg-type]
        grounding=FakeGrounding([SOURCE]),  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
    )
    result = await service.create_set(
        student_id="student",
        request=CreatePracticeSetRequest(
            topic_id="ml.logistic_regression",
            mode="practice",
            count=1,
        ),
    )

    public_json = result.model_dump_json()
    assert "answer_key" not in public_json
    assert "rubric" not in public_json
    assert "canonical_answer" not in public_json
    assert SOURCE["content"] not in public_json
    assert repository.saved.questions[0].answer_key.canonical_answer
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_practice_generation_refuses_empty_grounding_without_llm(tmp_path) -> None:
    llm = OneQuestionLLM()
    service = PracticeService(
        settings=settings(tmp_path),
        repository=FakeRepository(),  # type: ignore[arg-type]
        grounding=FakeGrounding([]),  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
    )

    with pytest.raises(KnowledgeInsufficientError):
        await service.create_set(
            student_id="student",
            request=CreatePracticeSetRequest(
                topic_id="ml.logistic_regression",
                count=1,
            ),
        )
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_model_knowledge_insufficient_envelope_maps_to_domain_error(tmp_path) -> None:
    repository = FakeRepository()
    llm = SequenceLLM(
        [
            {
                "status": "knowledge_insufficient",
                "message": "资料不足以支持可靠题目。",
                "missing_topic": "逻辑回归的似然推导",
            }
        ]
    )
    service = PracticeService(
        settings=settings(tmp_path),
        repository=repository,  # type: ignore[arg-type]
        grounding=FakeGrounding([SOURCE]),  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
    )

    with pytest.raises(KnowledgeInsufficientError) as captured:
        await service.create_set(
            student_id="student",
            request=CreatePracticeSetRequest(
                topic_id="ml.logistic_regression",
                mode="practice",
                count=3,
            ),
        )

    assert captured.value.code == "KNOWLEDGE_INSUFFICIENT"
    assert repository.saved is None
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_knowledge_insufficient_envelope_rejects_mixed_or_extra_fields(tmp_path) -> None:
    malformed = {
        "status": "knowledge_insufficient",
        "message": "资料不足。",
        "missing_topic": "似然推导",
        "questions": [],
    }
    repository = FakeRepository()
    llm = SequenceLLM([malformed, malformed])
    strict_settings = settings(tmp_path).model_copy(
        update={"question_generation_max_retries": 0}
    )
    service = PracticeService(
        settings=strict_settings,
        repository=repository,  # type: ignore[arg-type]
        grounding=FakeGrounding([SOURCE]),  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
    )

    with pytest.raises(StructuredOutputInvalidError):
        await service.create_set(
            student_id="student",
            request=CreatePracticeSetRequest(
                topic_id="ml.logistic_regression",
                mode="practice",
                count=1,
            ),
        )

    assert repository.saved is None
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_generated_rubric_is_scaled_to_100_without_changing_ratio(tmp_path) -> None:
    repository = FakeRepository()
    llm = SequenceLLM(
        [
            {
                "questions": [
                    generated_question(
                        question_id="q1",
                        question="交叉熵与伯努利似然有什么关系？",
                        rubric=[
                            {"criterion": "说明伯努利似然", "points": 30},
                            {"criterion": "说明负对数关系", "points": 20},
                        ],
                    )
                ]
            }
        ]
    )
    service = PracticeService(
        settings=settings(tmp_path),
        repository=repository,  # type: ignore[arg-type]
        grounding=FakeGrounding([SOURCE]),  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
    )

    await service.create_set(
        student_id="student",
        request=CreatePracticeSetRequest(
            topic_id="ml.logistic_regression",
            mode="practice",
            count=1,
        ),
    )

    points = [item.points for item in repository.saved.questions[0].rubric]
    assert sum(points) == pytest.approx(100)
    assert points[0] / points[1] == pytest.approx(30 / 20)
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_question_count_error_is_repaired_with_exact_count_diagnostic(tmp_path) -> None:
    first = {
        "questions": [
            generated_question(question_id="q1", question="第一道题是什么？")
        ]
    }
    second = {
        "questions": [
            generated_question(question_id="q1", question="第一道题是什么？"),
            generated_question(question_id="q2", question="第二道题是什么？"),
        ]
    }
    repository = FakeRepository()
    llm = SequenceLLM([first, second])
    service = PracticeService(
        settings=settings(tmp_path),
        repository=repository,  # type: ignore[arg-type]
        grounding=FakeGrounding([SOURCE]),  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
    )

    result = await service.create_set(
        student_id="student",
        request=CreatePracticeSetRequest(
            topic_id="ml.logistic_regression",
            mode="practice",
            count=2,
        ),
    )

    assert len(result.questions) == 2
    assert len(llm.calls) == 2
    repair_prompt = llm.calls[1][1]["content"]
    assert "questions must contain exactly 2 items" in repair_prompt
    assert "current count=1" in repair_prompt


@pytest.mark.asyncio
async def test_internal_source_ids_are_repaired_out_of_student_visible_question(
    tmp_path,
) -> None:
    leaked = {
        "questions": [
            generated_question(
                question_id="q1",
                question="请结合 S1，用自己的话解释交叉熵。",
            )
        ]
    }
    repaired = {
        "questions": [
            generated_question(
                question_id="q1",
                question="请用自己的话解释交叉熵与伯努利似然的关系。",
            )
        ]
    }
    repository = FakeRepository()
    llm = SequenceLLM([leaked, repaired])
    service = PracticeService(
        settings=settings(tmp_path),
        repository=repository,  # type: ignore[arg-type]
        grounding=FakeGrounding([SOURCE]),  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
    )

    result = await service.create_set(
        student_id="student",
        request=CreatePracticeSetRequest(
            topic_id="ml.logistic_regression",
            mode="practice",
            count=1,
        ),
    )

    assert result.questions[0].question == repaired["questions"][0]["question"]
    assert "S1" not in result.questions[0].question
    assert len(llm.calls) == 2
    assert "student-visible question/options" in llm.calls[1][1]["content"]
