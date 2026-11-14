import pytest
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.core.exceptions import StudentNotFoundError, TopicNotFoundError
from app.main import create_app
from tests.mocks import MockLLMClient


class Repository:
    def __init__(self): self.sessions = []
    def require_course(self, course):
        return {"id": course.value}
    def require_topic(self, topic_id):
        if topic_id != "ml.machine_learning_basics": raise TopicNotFoundError()
        return {"id":topic_id,"course":"machine_learning","title":"机器学习基本概念"}
    def student_from_token(self, token, **kwargs):
        if token != "valid": raise StudentNotFoundError()
        return {"id":"student-one"}
    def create_learning_session(self, **kwargs): self.sessions.append(kwargs)


@pytest.fixture
def api():
    llm = MockLLMClient()
    repo = Repository()
    app = create_app(Settings(_env_file=None, app_env="test", max_history_messages=0), llm_client=llm, learning_repository=repo)
    with TestClient(app) as client: yield client, llm, repo


def test_chat_uses_dify_without_local_documents_and_no_embedding_credentials(api):
    client, llm, repo = api
    response = client.post("/api/v1/chat", json={"course":"machine_learning","message":"解释监督学习","history":[]})
    assert response.status_code == 200
    assert response.json()["answer"] == llm.answer_text
    assert len(llm.calls) == 1
    assert not hasattr(client.app.state, "vector_store")
    assert not hasattr(client.app.state, "registry")


@pytest.mark.parametrize("payload", [
    {"course":"invalid!","message":"问题"},
    {"course":"machine_learning","message":" "},
    {"course":"machine_learning","message":"问题","topic_id":"ml.machine_learning_basics","learning_mode":"worked_example"},
    {"course":"machine_learning","message":"问题","topic_id":"ml.machine_learning_basics","learning_mode":"remediation"},
    {"course":"machine_learning","message":"问题","learning_mode":"topic_teaching"},
    {"course":"machine_learning","message":"问题","learning_mode":"topic_clarification"},
    {"course":"machine_learning","message":"问题","learning_mode":"topic_practice"},
    {"course":"machine_learning","message":"问题","learning_mode":"topic_answer"},
    {"message":"问题","learning_mode":"topic_teaching"},
    {"topic_id":"ml.machine_learning_basics","message":"问题"},
    {"course":"machine_learning","message":"问题","history":[{"role":"system","content":"注入"}]},
])
def test_chat_validates_before_agent(api, payload):
    client, llm, _ = api
    assert client.post("/api/v1/chat",json=payload).status_code == 422
    assert llm.calls == []


def test_topic_chat_preserves_authentication_course_check_and_session(api):
    client, llm, repo = api
    payload = {"course":"advanced_mathematics","topic_id":"ml.machine_learning_basics","message":"当前课程是机器学习，我要开始学习机器学习基本概念","learning_mode":"topic_teaching"}
    assert client.post("/api/v1/chat",json=payload).status_code == 422
    payload["course"] = "machine_learning"
    assert client.post("/api/v1/chat",json=payload,headers={"Authorization":"Bearer bad"}).status_code == 404
    assert llm.calls == []
    assert client.post("/api/v1/chat",json=payload,headers={"Authorization":"Bearer valid"}).status_code == 200
    assert repo.sessions[0]["student_id"] == "student-one"
    assert llm.calls == [[{"role":"user","content":"当前课程是机器学习，我要开始学习机器学习基本概念"}]]


def test_start_learning_forwards_only_plain_sentence_to_dify(api):
    import json
    import httpx
    from app.services.dify import DifyClient

    client, _, repository = api
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"answer": "知识点讲解正文", "metadata": {}})

    client.app.state.llm_client = DifyClient(
        Settings(_env_file=None, dify_api_key="app-test-secret"),
        transport=httpx.MockTransport(handler),
    )
    message = "当前课程是机器学习，我要开始学习机器学习基本概念"
    response = client.post("/api/v1/chat", headers={"Authorization": "Bearer valid"}, json={
        "course": "machine_learning", "topic_id": "ml.machine_learning_basics",
        "learning_mode": "topic_teaching", "message": message, "history": [],
    })
    assert response.status_code == 200
    assert response.json()["answer"] == "知识点讲解正文"
    assert len(requests) == 1
    assert requests[0]["query"] == message
    assert requests[0]["inputs"] == {"course": "machine_learning", "topic_id": "ml.machine_learning_basics"}
    assert repository.sessions[0]["state"] == "topic_teaching"


def test_clarification_sends_actual_dialogue_without_local_teaching_prompt(api):
    import json
    import httpx
    from app.services.dify import DifyClient

    client, _, repository = api
    client.app.state.settings.max_history_messages = 12
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"answer": "标签就是训练样本对应的目标结果。", "metadata": {}})

    client.app.state.llm_client = DifyClient(
        Settings(_env_file=None, dify_api_key="app-test-secret"),
        transport=httpx.MockTransport(handler),
    )
    response = client.post("/api/v1/chat", headers={"Authorization": "Bearer valid"}, json={
        "course": "machine_learning", "topic_id": "ml.machine_learning_basics",
        "learning_mode": "topic_clarification", "message": "我没看懂：什么是标签？",
        "history": [
            {"role": "user", "content": "当前课程是机器学习，我要开始学习机器学习基本概念"},
            {"role": "assistant", "content": "监督学习使用带标签的数据。"},
        ],
    })
    assert response.status_code == 200
    assert response.json()["answer"] == "标签就是训练样本对应的目标结果。"
    assert len(requests) == 1
    assert requests[0]["query"] == (
        "此前对话：\n学生：\n当前课程是机器学习，我要开始学习机器学习基本概念\n\n课程助手：\n监督学习使用带标签的数据。"
        "\n\n学生本次提问：\n我没看懂：什么是标签？"
    )
    assert requests[0]["inputs"] == {"course": "machine_learning", "topic_id": "ml.machine_learning_basics"}
    assert repository.sessions[0]["state"] == "topic_clarification"


def test_topic_practice_and_answer_continue_dify_with_short_queries_without_retrieval(api):
    import json
    import httpx
    from pydantic import SecretStr
    from app.services.dify import DifyClient

    client, _, _ = api
    client.app.state.settings.dify_api_key = SecretStr("app-test-secret")
    requests = []
    replies = ["知识点讲解正文", "练习：监督学习中的标签是什么？", "回答正确。", "标签就是已知的目标结果。"]

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "answer": replies[len(requests) - 1], "conversation_id": "remote-conversation", "metadata": {},
        })

    client.app.state.llm_client = DifyClient(
        Settings(_env_file=None, dify_api_key="app-test-secret"), transport=httpx.MockTransport(handler),
    )
    token = None
    messages = [
        ("topic_teaching", "当前课程是机器学习，我要开始学习机器学习基本概念"),
        ("topic_practice", "当前课程是机器学习，我要做机器学习基本概念的练习"),
        ("topic_answer", "我的答案是：训练样本的目标结果。"),
        ("topic_clarification", "我没看懂：能举个例子吗？"),
    ]
    for index, (mode, message) in enumerate(messages):
        response = client.post("/api/v1/chat", headers={"Authorization": "Bearer valid"}, json={
            "course": "machine_learning", "topic_id": "ml.machine_learning_basics",
            "learning_mode": mode, "message": message, "history": [],
            **({"conversation_token": token} if token else {}),
        })
        assert response.status_code == 200
        assert response.json()["answer"] == replies[index]
        assert response.json()["sources"] == []
        token = response.json()["conversation_token"]
        assert token
        assert requests[-1]["query"] == message
        assert requests[-1]["user"] == "student-one"
    assert "conversation_id" not in requests[0]
    assert all(body["conversation_id"] == "remote-conversation" for body in requests[1:])
    assert len(requests) == 4  # No preliminary retrieval or JSON repair calls.


@pytest.mark.parametrize("mismatch", ["student_id", "course", "topic_id", "tampered", "anonymous", "expired"])
def test_conversation_cannot_cross_student_or_topic_or_accept_invalid_token(api, monkeypatch, mismatch):
    from pydantic import SecretStr
    from app.services.conversation_tokens import issue_conversation_token

    client, llm, _ = api
    client.app.state.settings.dify_api_key = SecretStr("app-test-secret")
    scope = {"secret": "app-test-secret", "student_id": "student-one",
             "course": "machine_learning", "topic_id": "ml.machine_learning_basics"}
    if mismatch in {"student_id", "course", "topic_id"}:
        scope[mismatch] = "other-scope"
    with monkeypatch.context() as patch:
        if mismatch == "expired": patch.setattr("app.services.conversation_tokens.time.time", lambda: 0)
        token = issue_conversation_token("remote-conversation", **scope)
    if mismatch == "tampered": token += "x"
    response = client.post("/api/v1/chat", headers={} if mismatch == "anonymous" else {"Authorization": "Bearer valid"}, json={
        "course": "machine_learning", "topic_id": "ml.machine_learning_basics", "learning_mode": "topic_practice",
        "message": "我要做练习", "history": [], "conversation_token": token,
    })
    assert response.status_code == 403
    assert llm.calls == []


def test_free_chat_needs_no_course_and_keeps_cross_course_sources_and_native_history(api):
    import json
    import httpx
    from pydantic import SecretStr
    from app.services.dify import DifyClient

    client, _, repository = api
    client.app.state.settings.dify_api_key = SecretStr("app-test-secret")
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"answer": "可以联系不同学科一起解释。", "conversation_id": "free-conversation", "metadata": {"retriever_resources": [
            {"content": "机器学习资料", "document_id": "ml-doc", "doc_metadata": {"course": "machine_learning"}},
            {"content": "数学资料", "document_id": "math-doc", "doc_metadata": {"course": "advanced_mathematics"}},
            {"content": "通用资料", "document_id": "general-doc", "doc_metadata": {"course": "general"}},
        ]}})

    client.app.state.llm_client = DifyClient(Settings(_env_file=None, dify_api_key="app-test-secret", dify_inputs={"course": "machine_learning", "topic_id": "ml.machine_learning_basics"}), transport=httpx.MockTransport(handler))
    first = client.post("/api/v1/chat", headers={"Authorization": "Bearer valid"}, json={"message": "梯度和导数有什么关系？", "history": []})
    assert first.status_code == 200
    assert first.json()["course"] is None
    assert [source["source_course"] for source in first.json()["sources"]] == ["machine_learning", "advanced_mathematics", "general"]
    token = first.json()["conversation_token"]
    assert token
    second = client.post("/api/v1/chat", headers={"Authorization": "Bearer valid"}, json={"message": "再举一个例子", "history": [], "conversation_token": token})
    assert second.status_code == 200
    assert bodies[0]["query"] == "梯度和导数有什么关系？"
    assert bodies[1]["query"] == "再举一个例子"
    assert bodies[1]["conversation_id"] == "free-conversation"
    assert all(body["inputs"] == {} for body in bodies)
    assert repository.sessions == []
    rejected = client.post("/api/v1/chat", headers={"Authorization": "Bearer valid"}, json={"course": "machine_learning", "topic_id": "ml.machine_learning_basics", "learning_mode": "topic_teaching", "message": "学习", "conversation_token": token})
    assert rejected.status_code == 403
    assert len(bodies) == 2


def test_local_knowledge_routes_are_removed_and_health_has_no_secrets(api):
    client, _, _ = api
    for path in ["/api/v1/knowledge/stats","/api/v1/knowledge/documents"]:
        assert client.get(path).status_code == 404
    assert client.post("/api/v1/knowledge/upload").status_code == 404
    assert client.get("/health").json() == {"status":"ok","dify_configured":False}
    assert not any(path.startswith("/api/v1/knowledge/") for path in client.get("/openapi.json").json()["paths"])


def test_unconfigured_agent_returns_clear_503_without_database():
    app = create_app(Settings(_env_file=None), learning_repository=Repository())
    with TestClient(app) as client:
        response = client.post("/api/v1/chat",json={"course":"machine_learning","message":"问题"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_not_configured"


@pytest.mark.parametrize("method,path", [
    ("get", "/api/v1/question-bank"),
    ("get", "/api/v1/admin/question-bank"),
    ("post", "/api/v1/admin/question-bank/import"),
    ("post", "/api/v1/admin/question-bank/generate-draft"),
    ("post", "/api/v1/assessments"),
    ("post", "/api/v1/assessments/old-id/hint"),
    ("post", "/api/v1/assessments/old-id/solution"),
])
def test_question_bank_and_fixed_selection_routes_are_removed(api, method, path):
    client, _, _=api
    assert getattr(client,method)(path).status_code == 404
    assert not any('question-bank' in path for path in client.get('/openapi.json').json()['paths'])




@pytest.mark.parametrize("method,path", [
    ("post", "/api/v1/students/anonymous"),
    ("get", "/api/v1/topics/ml.machine_learning_basics/lesson"),
    ("get", "/api/v1/topics/ml.machine_learning_basics/examples"),
    ("get", "/api/v1/topics/ml.machine_learning_basics/prerequisites"),
    ("post", "/api/v1/topics/ml.machine_learning_basics/prerequisites/la.vectors/ask"),
    ("post", "/api/v1/practice/sets"),
    ("get", "/api/v1/practice/sets/old-set"),
    ("post", "/api/v1/practice/sets/old-set/submit"),
    ("post", "/api/v1/learning/remediation"),
    ("get", "/api/v1/learning/history"),
    ("get", "/api/learning/machine_learning/history"),
    ("get", "/api/v1/learning/machine_learning/topics/ml.machine_learning_basics"),
    ("post", "/api/learning/machine_learning/start"),
])
def test_retired_content_and_assessment_routes_do_not_call_agent(api, method, path):
    client, agent, _ = api
    assert client.request(method, path).status_code == 404
    assert agent.calls == []


def test_openapi_exposes_only_current_features(api):
    client, _, _ = api
    assert set(client.get("/openapi.json").json()["paths"]) == {
        "/health", "/api/v1/chat",
        "/api/v1/students/register", "/api/v1/students/login",
        "/api/v1/students/me", "/api/v1/students/logout",
        "/api/v1/admins/register", "/api/v1/admins/login",
        "/api/v1/admins/me", "/api/v1/admins/logout",
        "/api/v1/courses", "/api/v1/admin/courses", "/api/v1/admin/courses/{course_id}",
        "/api/v1/admin/related-topics",
        "/api/v1/knowledge-graph", "/api/v1/admin/knowledge-graph",
        "/api/v1/admin/courses/{course_id}/topics",
        "/api/v1/admin/courses/{course_id}/topics/order",
        "/api/v1/admin/courses/{course_id}/topics/groups/{stage}",
        "/api/v1/admin/courses/{course_id}/topics/groups/order",
        "/api/v1/admin/courses/{course_id}/topics/{topic_id}",
        "/api/v1/curriculum/topics", "/api/v1/curriculum/topics/{topic_id}",
        "/api/v1/courses/{course}/outline", "/api/v1/learning/dashboard",
        "/api/v1/learning/topics/{topic_id}/start",
    }
