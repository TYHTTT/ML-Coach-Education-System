from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.core.exceptions import StudentNotFoundError, TopicNotFoundError
from app.main import create_app
from tests.mocks import MockLLMClient


class Repository:
    def __init__(self): self.sessions = []
    def require_topic(self, topic_id):
        if topic_id != "ml.machine_learning_basics": raise TopicNotFoundError()
        return {"id":topic_id,"course":"machine_learning","title":"机器学习基本概念"}
    def student_from_token(self, token, **kwargs):
        if token != "valid": raise StudentNotFoundError()
        return {"id":"student-one"}
    def create_learning_session(self, **kwargs): self.sessions.append(kwargs)
    def list_prerequisites(self, topic_id): return []


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr("app.main.seed_curriculum", lambda repository: None)
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
    {"course":"invalid","message":"问题"},
    {"course":"machine_learning","message":" "},
    {"course":"machine_learning","message":"问题","learning_mode":"worked_example"},
    {"course":"machine_learning","message":"问题","history":[{"role":"system","content":"注入"}]},
])
def test_chat_validates_before_agent(api, payload):
    client, llm, _ = api
    assert client.post("/api/v1/chat",json=payload).status_code == 422
    assert llm.calls == []


def test_topic_chat_preserves_authentication_course_check_and_session(api):
    client, llm, repo = api
    payload = {"course":"advanced_mathematics","topic_id":"ml.machine_learning_basics","message":"讲解","learning_mode":"topic_teaching"}
    assert client.post("/api/v1/chat",json=payload).status_code == 422
    payload["course"] = "machine_learning"
    assert client.post("/api/v1/chat",json=payload,headers={"Authorization":"Bearer bad"}).status_code == 404
    assert llm.calls == []
    assert client.post("/api/v1/chat",json=payload,headers={"Authorization":"Bearer valid"}).status_code == 200
    assert repo.sessions[0]["student_id"] == "student-one"
    assert "机器学习基本概念" in llm.calls[0][-1]["content"]


def test_local_knowledge_routes_are_removed_and_health_has_no_secrets(api):
    client, _, _ = api
    for path in ["/api/v1/knowledge/stats","/api/v1/knowledge/documents"]:
        assert client.get(path).status_code == 404
    assert client.post("/api/v1/knowledge/upload").status_code == 404
    assert client.get("/health").json() == {"status":"ok","dify_configured":False}
    assert "knowledge" not in str(client.get("/openapi.json").json()["paths"])


def test_undeclared_prerequisite_is_rejected_before_agent(api):
    client, llm, _ = api
    result = client.post("/api/v1/topics/ml.machine_learning_basics/prerequisites/la.vectors/ask",json={"message":"补学"})
    assert result.status_code == 403
    assert llm.calls == []


def test_unconfigured_agent_returns_clear_503_without_database(monkeypatch):
    monkeypatch.setattr("app.main.seed_curriculum", lambda repository: None)
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


def test_prerequisite_requests_no_longer_accept_bank_generation():
    from pydantic import ValidationError
    from app.schemas.content import PrerequisiteTestRequest
    with pytest.raises(ValidationError):
        PrerequisiteTestRequest(topic_id='ml.linear_regression', generation_mode='bank')
