from __future__ import annotations

from pathlib import Path

from app.db.database import PostgresDatabase


SCHEMA_FILE = Path(__file__).resolve().parents[2] / "operations" / "database" / "initialize_postgresql.sql"


def test_postgres_schema_initialization_is_idempotent(postgres_test_database_url) -> None:
    database_url = postgres_test_database_url

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
            (["students", "administrators", "curriculum_topics", "practice_sets", "learning_sessions", "topic_placements"],),
        ).fetchall()

    assert {row["table_name"] for row in rows} == {
        "students",
        "administrators",
        "curriculum_topics",
        "practice_sets",
        "learning_sessions",
        "topic_placements",
    }


def test_new_schema_omits_retired_local_content_without_dropping_existing_data():
    schema = SCHEMA_FILE.read_text(encoding="utf-8")
    for table in ["lessons", "worked_examples", "content_exposures", "documents", "document_chunks", "question_bank"]:
        assert f"CREATE TABLE IF NOT EXISTS {table} (" not in schema
    assert "DROP TABLE" not in schema.upper()
