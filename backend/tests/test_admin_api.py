import logging
from pathlib import Path

from fastapi.testclient import TestClient
from psycopg.errors import UniqueViolation
import pytest

from app.core.config import Settings
from app.core.exceptions import AdminUnauthorizedError
from app.core.security import hash_password, verify_password
from app.main import create_app
from app.schemas.admin import RegisterAdminRequest
from tests.mocks import MockLLMClient


AUTHCODE = "test-admin-authorization-secret"
PAYLOAD = {"username": "admin_test", "password": "test-password", "display_name": "测试管理员", "authcode": AUTHCODE}


class FakeAdmins:
    def __init__(self):
        self.register_calls = []
        self.account = {"id": "admin-one", "username": "admin_test", "display_name": "测试管理员",
                        "created_at": "2026-11-12T08:00:00+00:00", "last_active_at": "2026-11-12T08:00:00+00:00",
                        "access_token": "admin-session"}
        self.valid = True

    def register(self, **kwargs):
        self.register_calls.append(kwargs)
        if len(self.register_calls) > 1:
            raise UniqueViolation()
        return self.account

    def login(self, *, username, password):
        return self.account if username == "admin_test" and password == "test-password" else None

    def from_token(self, token):
        if token != "admin-session" or not self.valid:
            raise AdminUnauthorizedError()
        return self.account

    def logout(self, token):
        self.valid = False


@pytest.fixture
def api():
    repository = FakeAdmins()
    app = create_app(Settings(_env_file=None, app_env="test", admin_authcode=AUTHCODE),
                     llm_client=MockLLMClient(), learning_repository=object(), admin_repository=repository)
    with TestClient(app) as client:
        yield client, repository


@pytest.mark.parametrize("authcode", ["wrong-code", "授权码错误", " " + AUTHCODE])
def test_wrong_authcode_cannot_create_administrator(api, authcode):
    client, repository = api
    response = client.post("/api/v1/admins/register", json={**PAYLOAD, "authcode": authcode})
    assert response.status_code == 403
    assert repository.register_calls == []
    assert AUTHCODE not in response.text


def test_missing_authcode_and_empty_configuration_disable_creation(api):
    client, repository = api
    assert client.post("/api/v1/admins/register", json={key: value for key, value in PAYLOAD.items() if key != "authcode"}).status_code == 422
    client.app.state.settings = Settings(_env_file=None)
    assert client.post("/api/v1/admins/register", json=PAYLOAD).status_code == 503
    assert repository.register_calls == []
    assert client.post("/api/v1/admins/login", json={"username": "admin_test", "password": "test-password"}).status_code == 200


def test_register_returns_only_public_profile_and_rejects_duplicate_username(api):
    client, repository = api
    created = client.post("/api/v1/admins/register", json=PAYLOAD)
    assert created.status_code == 201
    assert set(created.json()) == {"admin_id", "username", "display_name", "role", "created_at", "last_active_at", "access_token"}
    assert created.json()["role"] == "admin"
    assert AUTHCODE not in created.text and PAYLOAD["password"] not in created.text
    assert "authcode" not in repository.register_calls[0]
    assert client.post("/api/v1/admins/register", json=PAYLOAD).status_code == 409


@pytest.mark.parametrize("authorization", [None, "Basic admin-session", "Bearer student-session", "Bearer invalid"])
def test_protected_admin_route_rejects_missing_invalid_and_student_sessions(api, authorization):
    client, _ = api
    headers = {"Authorization": authorization} if authorization else {}
    assert client.get("/api/v1/admins/me", headers=headers).status_code == 401
    assert client.post("/api/v1/admins/logout", headers=headers).status_code == 401


def test_login_profile_and_logout_revoke_access(api):
    client, _ = api
    assert client.post("/api/v1/admins/login", json={"username": "admin_test", "password": "incorrect"}).status_code == 401
    login = client.post("/api/v1/admins/login", json={"username": "admin_test", "password": "test-password"})
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    profile = client.get("/api/v1/admins/me", headers=headers)
    assert profile.status_code == 200
    assert "access_token" not in profile.json()
    assert client.post("/api/v1/admins/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/admins/me", headers=headers).status_code == 401


def test_authcode_and_password_are_not_exposed_in_repr_or_validation_logs(api, caplog):
    request = RegisterAdminRequest.model_validate(PAYLOAD)
    assert AUTHCODE not in repr(request) and PAYLOAD["password"] not in repr(request)
    client, _ = api
    secret = "validation-input-secret-unique"
    with caplog.at_level(logging.INFO):
        response = client.post("/api/v1/admins/register", json={**PAYLOAD, "authcode": secret * 40})
    assert response.status_code == 422
    assert secret not in caplog.text and secret not in response.text
    assert AUTHCODE not in repr(Settings(_env_file=None, admin_authcode=AUTHCODE))


def test_shared_password_hashing_preserves_existing_student_format():
    encoded = hash_password("student-password")
    assert encoded.startswith("pbkdf2_sha256$600000$")
    assert verify_password("student-password", encoded)
    assert not verify_password("wrong", encoded)
    assert not verify_password("student-password", "invalid")


def test_admin_migration_matches_fresh_install_and_adds_one_table():
    root = Path(__file__).resolve().parents[2]
    migration = (root / "operations/database/add_administrators.sql").read_text(encoding="utf-8").strip()
    fresh = (root / "operations/database/initialize_postgresql.sql").read_text(encoding="utf-8")
    assert migration in fresh
    assert migration.count("CREATE TABLE") == 1
    assert "DROP" not in migration.upper()


@pytest.fixture
def database_api(postgres_test_database_url):
    settings = Settings(_env_file=None, app_env="test", database_url=postgres_test_database_url, admin_authcode=AUTHCODE)
    app = create_app(settings, llm_client=MockLLMClient())
    with TestClient(app) as client:
        yield client, app.state.admin_repository, app.state.learning_repository


def test_database_accounts_are_separate_and_hashes_are_not_plaintext(database_api):
    client, admins, students = database_api
    student = students.register_student(username="admin_test", password="student-password", display_name="同名学生")
    created = client.post("/api/v1/admins/register", json=PAYLOAD)
    assert created.status_code == 201
    account = created.json()
    with admins.database.connect() as connection:
        row = connection.execute("SELECT * FROM administrators WHERE id=?", (account["admin_id"],)).fetchone()
        assert verify_password(PAYLOAD["password"], row["password_hash"])
        assert row["password_hash"] != PAYLOAD["password"]
        assert row["session_token_hash"] != account["access_token"]
    assert students.student_from_token(student["access_token"])["id"] == student["id"]
    assert client.get("/api/v1/admins/me", headers={"Authorization": "Bearer " + student["access_token"]}).status_code == 401
    assert client.get("/api/v1/students/me", headers={"Authorization": "Bearer " + account["access_token"]}).status_code == 404
    assert client.post("/api/v1/admins/register", json=PAYLOAD).status_code == 409


def test_database_login_rotation_expiry_disable_and_revocation(database_api):
    client, admins, _ = database_api
    first = client.post("/api/v1/admins/register", json=PAYLOAD).json()
    assert client.post("/api/v1/admins/login", json={"username": "admin_test", "password": "wrong"}).status_code == 401
    second = client.post("/api/v1/admins/login", json={"username": "ADMIN_TEST", "password": PAYLOAD["password"]}).json()
    old_headers = {"Authorization": "Bearer " + first["access_token"]}
    headers = {"Authorization": "Bearer " + second["access_token"]}
    assert second["access_token"] != first["access_token"]
    assert client.get("/api/v1/admins/me", headers=old_headers).status_code == 401
    assert client.get("/api/v1/admins/me", headers=headers).status_code == 200
    with admins.database.connect() as connection:
        connection.execute("UPDATE administrators SET session_expires_at='2000-01-01T00:00:00+00:00'")
    assert client.get("/api/v1/admins/me", headers=headers).status_code == 401
    third = client.post("/api/v1/admins/login", json={"username": "admin_test", "password": PAYLOAD["password"]}).json()
    headers = {"Authorization": "Bearer " + third["access_token"]}
    with admins.database.connect() as connection:
        connection.execute("UPDATE administrators SET active=0")
    assert client.get("/api/v1/admins/me", headers=headers).status_code == 401
    assert client.post("/api/v1/admins/login", json={"username": "admin_test", "password": PAYLOAD["password"]}).status_code == 401
    with admins.database.connect() as connection:
        connection.execute("UPDATE administrators SET active=1")
    assert client.post("/api/v1/admins/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/admins/me", headers=headers).status_code == 401
