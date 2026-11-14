from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import psycopg
from psycopg.rows import dict_row


class PostgresConnection:
    """Small compatibility wrapper around a PostgreSQL connection."""

    def __init__(self, connection: psycopg.Connection[dict[str, Any]]) -> None:
        self._connection = connection

    def __enter__(self) -> "PostgresConnection":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        try:
            if exc_type is None:
                self._connection.commit()
            else:
                self._connection.rollback()
        finally:
            self._connection.close()
        return False

    @staticmethod
    def _adapt_query(query: str) -> str:
        return query.replace("?", "%s")

    def execute(self, query: str, params: Sequence[Any] | None = None) -> Any:
        return self._connection.execute(self._adapt_query(query), params)

    def executemany(self, query: str, params_seq: Sequence[Sequence[Any]]) -> Any:
        with self._connection.cursor() as cursor:
            return cursor.executemany(self._adapt_query(query), params_seq)

    def execute_script(self, script: str) -> None:
        self._connection.execute(script, prepare=False)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()


class PostgresDatabase:
    """PostgreSQL connection factory shared by repositories and migrations."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def connect(self) -> PostgresConnection:
        connection = psycopg.connect(self.database_url, row_factory=dict_row)
        return PostgresConnection(connection)


def connect_postgres(database_url: str) -> PostgresConnection:
    return PostgresDatabase(database_url).connect()
