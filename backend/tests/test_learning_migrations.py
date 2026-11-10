from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.db.database import PostgresDatabase


SCHEMA_FILE = Path(__file__).resolve().parents[2] / "operations" / "database" / "initialize_postgresql.sql"


def test_postgres_schema_initialization_is_idempotent() -> None:
    database_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("需要专用的 POSTGRES_TEST_DATABASE_URL 才运行 PostgreSQL 架构集成测试")

    schema = SCHEMA_FILE.read_text(encoding="utf-8")
    database = PostgresDatabase(database_url)
    with database.connect() as connection:
        connection.execute_script(schema)
    with database.connect() as connection:
        connection.execute_script(schema)
        rows = connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = ANY(%s)
            """,
            (["students", "curriculum_topics", "practice_sets", "worked_examples", "lessons"],),
        ).fetchall()

    assert {row["table_name"] for row in rows} == {
        "students",
        "curriculum_topics",
        "practice_sets",
        "worked_examples",
        "lessons",
    }
