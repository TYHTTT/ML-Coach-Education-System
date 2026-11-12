from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from psycopg.conninfo import conninfo_to_dict

from app.db.database import PostgresDatabase


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
            WHERE schemaname = 'public'
            """
        ).fetchall()
        connection.execute(
            "TRUNCATE TABLE " + ", ".join(row["name"] for row in tables) + " RESTART IDENTITY CASCADE"
        )
        connection.execute_script(schema_path.read_text(encoding="utf-8"))
    yield database_url
