from __future__ import annotations

from app.services.dify import resource_snapshots


class MockLLMClient:
    def __init__(self, answer: str = "这是基于课程资料的测试回答。[S1]") -> None:
        self.answer_text = answer
        self.calls: list[list[dict[str, str]]] = []

    async def answer(self, *, course, question, history, topic_id=None, user=None, conversation_id=None):
        self.calls.append([*history, {"role": "user", "content": question}])
        sources = resource_snapshots(getattr(self, "resources", []), course=course)
        return {
            "answer": self.answer_text, "course": course,
            "sources": [{**source, "snippet": source["content"]} for source in sources],
            "retrieval_count": len(sources),
        }
