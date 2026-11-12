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
        assert body["query"] == "此前对话：\n学生：\n此前的问题\n\n学生本次提问：\n解释"
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
        assert (await agent.run("问题"))["answer"] == "替换后的回答"
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
            await agent.run("问题")
    finally:
        await agent.close()


@pytest.mark.asyncio
async def test_http_failures_do_not_expose_upstream_body_or_secret():
    agent = client(lambda request: httpx.Response(401, text="app-test-secret upstream debug"))
    try:
        with pytest.raises(LLMServiceError) as error:
            await agent.run("问题")
        assert "app-test-secret" not in str(error.value)
        assert "upstream debug" not in error.value.message
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
        first = await agent.answer(course=Course.MACHINE_LEARNING, question="开始学习", history=[], user="student-1")
        assert first["conversation_id"] == "conversation-one"
        result = await agent.answer(
            course=Course.MACHINE_LEARNING, question="我要做练习", user="student-1",
            history=[{"role": "assistant", "content": "此前很长的讲解正文"}], conversation_id=first["conversation_id"],
        )
        assert result["answer"] == "练习题正文"
        assert bodies[1]["query"] == "我要做练习"
        assert bodies[1]["conversation_id"] == "conversation-one"
        assert bodies[0]["user"] == bodies[1]["user"]
        assert "conversation_id" not in bodies[0]
    finally:
        await agent.close()
