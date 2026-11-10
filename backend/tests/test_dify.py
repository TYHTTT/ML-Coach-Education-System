import json

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import LLMServiceError
from app.core.types import Course
from app.services.dify import DifyClient


def client(handler):
    return DifyClient(Settings(_env_file=None, dify_api_base_url="https://dify.example/v1/",
                               dify_api_key="app-test-secret", dify_inputs={"tenant": "school"}),
                      transport=httpx.MockTransport(handler))


def sse(events):
    return httpx.Response(200, headers={"Content-Type": "text/event-stream"},
                          text=": ping\n\n" + "".join("data: " + json.dumps(event, ensure_ascii=False) + "\n\n" for event in events))


@pytest.mark.asyncio
async def test_agent_stream_history_inputs_credentials_and_remote_citations():
    requests = []
    def handler(request):
        requests.append(request)
        return sse([
            {"event": "agent_thought", "thought": "hidden reasoning"},
            {"event": "agent_message", "answer": "监督"},
            {"event": "agent_message", "answer": "学习"},
            {"event": "message_end", "metadata": {"retriever_resources": [
                {"content": "训练使用带标签数据", "document_id": "remote-doc", "segment_id": "remote-segment", "document_name": "Dify 课件"}
            ]}},
        ])
    agent = client(handler)
    try:
        result = await agent.answer(course=Course.MACHINE_LEARNING, question="解释", history=[{"role":"user","content":"此前的问题"}], topic_id="ml.machine_learning_basics", user="student-1")
        assert result["answer"] == "监督学习"
        assert result["sources"][0]["document_id"] == "remote-doc"
        assert result["retrieval_count"] == 1
        request = requests[0]
        assert str(request.url) == "https://dify.example/v1/chat-messages"
        assert request.headers["Authorization"] == "Bearer app-test-secret"
        body = json.loads(request.content)
        assert body["response_mode"] == "streaming"
        assert body["user"] == "student-1"
        assert body["inputs"] == {"course":"machine_learning", "topic_id":"ml.machine_learning_basics", "tenant":"school"}
        assert json.loads(body["query"])["messages"][1]["content"] == "此前的问题"
        assert "conversation_id" not in body
    finally:
        await agent.close()


@pytest.mark.asyncio
async def test_message_replace_replaces_partial_answer_and_ignores_thoughts():
    agent = client(lambda request: sse([
        {"event":"message","answer":"未完成"},
        {"event":"message_replace","answer":"替换后的回答"},
        {"event":"message_end","metadata":{}},
    ]))
    try:
        assert await agent.generate([{"role":"user","content":"问题"}]) == "替换后的回答"
    finally:
        await agent.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("events", [
    [{"event":"agent_message","answer":"部分回答"}],
    [{"event":"error","message":"secret upstream details"}],
    [{"event":"message_end"}],
])
async def test_agent_errors_empty_and_truncated_streams_are_rejected(events):
    agent = client(lambda request: sse(events))
    try:
        with pytest.raises(LLMServiceError):
            await agent.generate([{"role":"user","content":"问题"}])
    finally:
        await agent.close()


@pytest.mark.asyncio
async def test_http_failures_do_not_expose_upstream_body_or_secret():
    agent = client(lambda request: httpx.Response(401, text="app-test-secret upstream debug"))
    try:
        with pytest.raises(LLMServiceError) as error:
            await agent.generate([{"role":"user","content":"问题"}])
        assert "app-test-secret" not in str(error.value)
        assert "upstream debug" not in error.value.message
    finally:
        await agent.close()


@pytest.mark.asyncio
async def test_structured_generation_is_unchanged_and_tasks_use_independent_users():
    bodies = []
    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"answer":'{"questions": []}', "metadata":{}})
    agent = client(handler)
    try:
        for _ in range(2):
            assert await agent.generate([{"role":"system","content":"只返回 JSON"}]) == '{"questions": []}'
        assert bodies[0]["user"] != bodies[1]["user"]
    finally:
        await agent.close()


@pytest.mark.asyncio
async def test_structured_tasks_and_json_repairs_keep_course_inputs():
    from pydantic import BaseModel
    from app.services.llm.base import for_learning_task
    from app.services.structured_output import generate_validated

    class Result(BaseModel):
        answer: int

    bodies = []
    def handler(request):
        bodies.append(json.loads(request.content))
        answer = "invalid" if len(bodies) == 1 else '{"answer": 42}'
        return httpx.Response(200, json={"answer": answer})
    agent = client(handler)
    try:
        result = await generate_validated(
            llm_client=for_learning_task(agent, Course.LINEAR_ALGEBRA, "la.dot_product"),
            messages=[{"role":"user","content":"计算内积"}], model=Result, temperature=0,
        )
        assert result.answer == 42
        assert len(bodies) == 2
        assert all(body["inputs"]["course"] == "linear_algebra" and body["inputs"]["topic_id"] == "la.dot_product" for body in bodies)
    finally:
        await agent.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("carrier", ["json", "message", "message_end"])
async def test_native_topic_conversation_keeps_query_short_and_captures_remote_id(carrier):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        if carrier == "json":
            return httpx.Response(200, json={"answer": "练习题正文", "conversation_id": "conversation-one"})
        events = [{"event": "agent_message", "answer": "练习题正文"}, {"event": "message_end"}]
        events[0 if carrier == "message" else 1]["conversation_id"] = "conversation-one"
        return sse(events)

    agent = client(handler)
    try:
        first = await agent.answer(course=Course.MACHINE_LEARNING, question="开始学习", history=[], plain_query=True, user="student-1")
        assert first["conversation_id"] == "conversation-one"
        result = await agent.answer(
            course=Course.MACHINE_LEARNING, question="我要做练习", plain_query=True, user="student-1",
            history=[{"role": "assistant", "content": "此前很长的讲解正文"}], conversation_id=first["conversation_id"],
        )
        assert result["answer"] == "练习题正文"
        assert bodies[1]["query"] == "我要做练习"
        assert bodies[1]["conversation_id"] == "conversation-one"
        assert bodies[0]["user"] == bodies[1]["user"]
        assert "conversation_id" not in bodies[0]
    finally:
        await agent.close()
