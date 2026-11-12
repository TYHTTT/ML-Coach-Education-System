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

    async def run(self, query: str, *, course: Course | None = None,
                  topic_id: str | None = None, user: str | None = None,
                  conversation_id: str | None = None) -> dict:
        key = self.settings.dify_api_key.get_secret_value().strip()
        if not key or not self.settings.dify_api_base_url.strip():
            raise ConfigurationError("请在后端配置 DIFY_API_BASE_URL 和 DIFY_API_KEY")
        payload = {
            "inputs": {**{key: value for key, value in self.settings.dify_inputs.items() if key not in {"course", "topic_id"}},
                       **({"course": course.value} if course else {}),
                       **({"topic_id": topic_id} if topic_id else {})},
            "query": query,
            "response_mode": "streaming",
            "user": user or f"course-coach-{uuid4().hex}",
            "auto_generate_name": False,
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        answer = ""
        remote_conversation_id = conversation_id
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
                    remote_conversation_id = body.get("conversation_id") or remote_conversation_id
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
                        remote_conversation_id = event.get("conversation_id") or remote_conversation_id
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
        return {"answer": answer, "resources": resources if isinstance(resources, list) else [],
                "conversation_id": remote_conversation_id}

    async def answer(self, *, course: Course | None, question: str, history: list[dict[str, str]],
                     topic_id: str | None = None, user: str | None = None,
                     conversation_id: str | None = None) -> dict:
        query = question
        if history and not conversation_id:
            transcript = "\n\n".join(
                f"{'学生' if item['role'] == 'user' else '课程助手'}：\n{item['content']}"
                for item in history
            )
            query = f"此前对话：\n{transcript}\n\n学生本次提问：\n{question}"
        result = await self.run(query, course=course, topic_id=topic_id, user=user, conversation_id=conversation_id)
        sources = resource_snapshots(result["resources"], course=course)
        return {"answer": result["answer"], "course": course,
                "sources": [{**item, "snippet": item["content"][:600]} for item in sources],
                "retrieval_count": len(sources), "conversation_id": result.get("conversation_id")}


def resource_snapshots(resources: list, *, course: Course | None) -> list[dict]:
    """Keep actual Dify citations; ignore explicitly foreign course metadata."""
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
        if course and source_course and source_course != course.value:
            continue
        try:
            resolved_course = course or (Course(source_course) if source_course else None)
        except ValueError:
            resolved_course = None
        identity = resource.get("segment_id") or (resource.get("document_id"), resource["content"])
        if identity in seen:
            continue
        seen.add(identity)
        snapshots.append({
            "source_id": f"S{len(snapshots) + 1}", "source_course": resolved_course.value if resolved_course else None,
            "topic_id": topic_id, "document_id": str(resource.get("document_id") or "dify"),
            "source_file": str(resource.get("document_name") or resource.get("dataset_name") or "Dify 课程资料"),
            "title": str(resource.get("document_name") or "Dify 课程资料"),
            "chapter": None, "section": None, "page": None,
            "chunk_index": len(snapshots), "content": resource["content"],
        })
    return snapshots
