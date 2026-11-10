from __future__ import annotations

class MockLLMClient:
    def __init__(self, answer: str = "这是基于课程资料的测试回答。[S1]") -> None:
        self.answer_text = answer
        self.calls: list[list[dict[str, str]]] = []

    async def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
    ) -> str:
        self.calls.append(messages)
        return self.answer_text

    async def run(self, messages, **kwargs):
        self.calls.append(messages)
        return {"answer": self.answer_text, "resources": getattr(self, "resources", [])}

    async def answer(self, *, course, question, history, system_prompt=None, topic_id=None, user=None, plain_query=False):
        from app.services.dify import resource_snapshots
        result = await self.run(([{"role": "user", "content": question}] if plain_query else [{"role": "system", "content": system_prompt or "课程辅导"}, *history, {"role": "user", "content": question}]))
        sources = resource_snapshots(result["resources"], course=course)
        return {"answer": result["answer"], "course": course, "sources": [{**s,"snippet":s["content"]} for s in sources], "retrieval_count": len(sources)}
