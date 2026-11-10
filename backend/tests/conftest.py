from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from psycopg.conninfo import conninfo_to_dict
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.database import PostgresDatabase
from app.main import create_app
from tests.mocks import MockLLMClient


@pytest.fixture
def postgres_test_database_url() -> Iterator[str]:
    database_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("需要 POSTGRES_TEST_DATABASE_URL 才运行 PostgreSQL 集成测试")

    database_name = conninfo_to_dict(database_url).get("dbname", "")
    if "test" not in database_name.lower():
        pytest.fail("POSTGRES_TEST_DATABASE_URL 必须指向名称包含 test 的专用数据库")

    schema_path = Path(__file__).resolve().parents[2] / "operations" / "database" / "initialize_postgresql.sql"
    database = PostgresDatabase(database_url)
    with database.connect() as connection:
        connection.execute_script(schema_path.read_text(encoding="utf-8"))
        tables = connection.execute(
            """
            SELECT quote_ident(tablename) AS name
            FROM pg_tables
            WHERE schemaname = 'public' AND tablename <> 'courses'
            """
        ).fetchall()
        connection.execute(
            "TRUNCATE TABLE " + ", ".join(row["name"] for row in tables) + " RESTART IDENTITY CASCADE"
        )
    yield database_url


@pytest.fixture
def settings(tmp_path, postgres_test_database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=postgres_test_database_url,
    )


@pytest.fixture
def mock_llm() -> MockLLMClient:
    return MockLLMClient()


@pytest.fixture
def client(
    settings: Settings,
    mock_llm: MockLLMClient,
) -> Iterator[TestClient]:
    application = create_app(
        settings,
        llm_client=mock_llm,
    )
    with TestClient(application) as test_client:
        yield test_client
