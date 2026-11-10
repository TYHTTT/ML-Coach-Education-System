"""Server-side Dify Agent transport shared by chat and learning tasks."""
from __future__ import annotations

import json
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, LLMServiceError
from app.core.types import Course


class DifyClient:
    def __init__(self, settings: Settings, *, transport=None) -> None:
        self.settings = settings
        self.http = httpx.AsyncClient(timeout=settings.dify_timeout_seconds, transport=transport)

    async def close(self) -> None:
        await self.http.aclose()

    async def run(self, messages: list[dict[str, str]] | str, *, course: Course | None = None,
                  topic_id: str | None = None, user: str | None = None) -> dict:
        key = self.settings.dify_api_key.get_secret_value().strip()
        if not key or not self.settings.dify_api_base_url.strip():
            raise ConfigurationError("请在后端配置 DIFY_API_BASE_URL 和 DIFY_API_KEY")
        # Each operation is independent. Browser history is supplied explicitly;
        # never reuse a remote conversation across courses or grading tasks.
        payload = {
            "inputs": {**self.settings.dify_inputs,
                       **({"course": course.value} if course else {}),
                       **({"topic_id": topic_id} if topic_id else {})},
            "query": messages if isinstance(messages, str) else json.dumps({"messages": messages}, ensure_ascii=False),
            "response_mode": "streaming",
            "user": user or f"course-coach-{uuid4().hex}",
            "auto_generate_name": False,
        }
        answer = ""
        metadata = {}
        ended = False
        try:
            async with self.http.stream(
                "POST", self.settings.dify_api_base_url.rstrip("/") + "/chat-messages",
                headers={"Authorization": f"Bearer {key}"}, json=payload,
            ) as response:
                response.raise_for_status()
                if "application/json" in response.headers.get("content-type", ""):
                    body = json.loads(await response.aread())
                    answer = body.get("answer", "")
                    metadata = body.get("metadata") or {}
                    ended = True
                else:
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        event = json.loads(data)
                        kind = event.get("event")
                        if kind == "error":
                            raise LLMServiceError("Dify Agent 处理失败，请检查应用配置后重试")
                        if kind in {"message", "agent_message"}:
                            answer += event.get("answer", "")
                        elif kind == "message_replace":
                            answer = event.get("answer", "")
                        elif kind == "message_end":
                            metadata = event.get("metadata") or {}
                            ended = True
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
            # Do not return upstream response bodies, headers, or credentials.
            raise LLMServiceError("Dify 服务请求失败，请检查服务地址、密钥或稍后重试",
                                  internal_message=f"Dify transport: {type(exc).__name__}") from None
        if not ended or not isinstance(answer, str) or not answer.strip():
            raise LLMServiceError("Dify 返回了空回答或未完整结束的响应，请重试")
        resources = metadata.get("retriever_resources", []) if isinstance(metadata, dict) else []
        return {"answer": answer, "resources": resources if isinstance(resources, list) else []}

    async def generate(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        # Sampling and model selection are configured on the published Dify app.
        return (await self.run(messages))["answer"]

    def for_task(self, course: Course, topic_id: str) -> DifyTaskClient:
        return DifyTaskClient(self, course, topic_id)

    async def answer(self, *, course: Course, question: str, history: list[dict[str, str]],
                     system_prompt: str | None = None, topic_id: str | None = None,
                     user: str | None = None, plain_query: bool = False) -> dict:
        messages: str | list[dict[str, str]]
        if plain_query:
            messages = question
            if history:
                transcript = "\n\n".join(
                    f"{'学生' if item['role'] == 'user' else '课程助手'}：\n{item['content']}"
                    for item in history
                )
                messages = f"此前对话：\n{transcript}\n\n学生本次提问：\n{question}"
        else:
            messages = self._chat_messages(course, question, history, system_prompt, topic_id)
        result = await self.run(messages, course=course, topic_id=topic_id, user=user)
        sources = resource_snapshots(result["resources"], course=course)
        return {"answer": result["answer"], "course": course,
                "sources": [{**item, "snippet": item["content"][:600]} for item in sources],
                "retrieval_count": len(sources)}

    @staticmethod
    def _chat_messages(course: Course, question: str, history: list[dict[str, str]],
                       system_prompt: str | None, topic_id: str | None) -> list[dict[str, str]]:
        prompt = f"你是中文课程辅导助手。当前课程：{course.display_name}。仅使用该课程的资料；资料不足时如实说明，不得编造引用。"
        if topic_id:
            prompt += f"当前知识点：{topic_id}。"
        if system_prompt:
            prompt += "\n" + system_prompt
        return [{"role": "system", "content": prompt}, *history, {"role": "user", "content": question}]


class DifyTaskClient:
    """Immutable scope for generation and repairs using the shared transport."""

    def __init__(self, agent: DifyClient, course: Course, topic_id: str) -> None:
        self.agent = agent
        self.course = course
        self.topic_id = topic_id

    async def generate(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        result = await self.agent.run(messages, course=self.course, topic_id=self.topic_id)
        return result["answer"]


def resource_snapshots(resources: list, *, course: Course, topic_ids: list[str] | None = None) -> list[dict]:
    """Keep actual Dify evidence; ignore explicitly foreign course/topic metadata."""
    snapshots = []
    seen = set()
    for resource in resources:
        if not isinstance(resource, dict) or not isinstance(resource.get("content"), str) or not resource["content"].strip():
            continue
        metadata = resource.get("doc_metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        source_course = metadata.get("course")
        topic_id = metadata.get("topic_id")
        if source_course and source_course != course.value:
            continue
        if topic_ids is not None and (source_course != course.value or topic_id not in topic_ids):
            continue
        identity = resource.get("segment_id") or (resource.get("document_id"), resource["content"])
        if identity in seen:
            continue
        seen.add(identity)
        snapshots.append({
            "source_id": f"S{len(snapshots) + 1}", "source_course": course.value,
            "topic_id": topic_id, "document_id": str(resource.get("document_id") or "dify"),
            "source_file": str(resource.get("document_name") or resource.get("dataset_name") or "Dify 课程资料"),
            "title": str(resource.get("document_name") or "Dify 课程资料"),
            "chapter": None, "section": None, "page": None,
            "chunk_index": len(snapshots), "content": resource["content"],
        })
    return snapshots
