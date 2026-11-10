import pytest
from app.core.types import Course
from app.services.learning_grounding import LearningGroundingService


class Agent:
    def __init__(self, resources): self.resources=resources; self.calls=[]
    async def run(self, messages, **kwargs):
        self.calls.append((messages,kwargs))
        return {"answer":"Agent 回答不能冒充原文", "resources":self.resources}


def resource(course="machine_learning", topic="ml.logistic_regression"):
    return {"content":"伯努利似然对应交叉熵", "document_id":"remote-document", "document_name":"逻辑回归", "doc_metadata":{"course":course,"topic_id":topic}}


@pytest.mark.asyncio
async def test_grounding_uses_remote_evidence_and_context():
    agent=Agent([resource()])
    result=await LearningGroundingService(agent=agent).retrieve(course=Course.MACHINE_LEARNING,topic={"id":"ml.logistic_regression","title":"逻辑回归"},purpose="practice_generation",user_question="损失函数")
    assert result.source_snapshot[0]["content"] == "伯努利似然对应交叉熵"
    assert result.source_ids == {"S1"}
    assert result.source_summary[0]["source_file"] == "逻辑回归"
    assert agent.calls[0][1]["course"] == Course.MACHINE_LEARNING
    assert "损失函数" in agent.calls[0][0][-1]["content"]


@pytest.mark.asyncio
async def test_missing_citations_never_turn_agent_answer_into_source():
    result=await LearningGroundingService(agent=Agent([])).retrieve(course=Course.MACHINE_LEARNING,topic={"id":"ml.logistic_regression"},purpose="practice_generation")
    assert result.source_snapshot == []


@pytest.mark.asyncio
async def test_empty_scope_skips_remote_call():
    agent=Agent([resource()])
    result=await LearningGroundingService(agent=agent).retrieve(course=Course.MACHINE_LEARNING,topic={"id":"ml.logistic_regression"},purpose="practice_generation",topic_ids=[])
    assert result.source_snapshot == [] and not agent.calls
