"""Back up and remove database objects belonging to retired website features."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from app.core.config import Settings


SQL_FILE = Path(__file__).with_name("remove_retired_features.sql")
BACKUP_DIRECTORY = Path(__file__).with_name("backups")
RETIRED_TABLES = (
    "content_review_events", "question_bank_topics", "question_bank_items",
    "assessment_blueprints", "content_exposures", "worked_examples", "lessons",
    "document_chunks", "documents",
)
RETIRED_COLUMNS = {
    "practice_sets": ("blueprint_id",),
    "practice_questions": ("bank_item_id", "item_version", "solution_steps_json"),
}


def inspect_database(connection) -> dict:
    existing = {row["tablename"] for row in connection.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
    )}
    tables = {}
    for name in RETIRED_TABLES:
        if name in existing:
            tables[name] = connection.execute(
                sql.SQL("SELECT count(*) AS count FROM public.{}").format(sql.Identifier(name))
            ).fetchone()["count"]
    columns = {}
    for table, candidates in RETIRED_COLUMNS.items():
        found = [row["column_name"] for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s AND column_name=ANY(%s) ORDER BY column_name",
            (table, list(candidates)),
        )]
        if found:
            columns[table] = found
    vector = bool(connection.execute("SELECT 1 FROM pg_extension WHERE extname='vector'").fetchone())
    return {"tables": tables, "columns": columns, "vector": vector}


def _create_backup(database_url: str, directory: Path, pg_dump: str | None) -> Path:
    executable = pg_dump or shutil.which("pg_dump")
    if not executable:
        raise RuntimeError("未找到 pg_dump，请安装 PostgreSQL 客户端或指定 --pg-dump 路径。")
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = directory / f"before-retired-cleanup-{stamp}-{uuid4().hex[:8]}.backup"
    environment = os.environ.copy()
    # Pass connection details through the environment; never print credentials
    # or place the password in the subprocess command line.
    environment_names = {"dbname": "PGDATABASE", "user": "PGUSER", "password": "PGPASSWORD",
                         "application_name": "PGAPPNAME", "client_encoding": "PGCLIENTENCODING"}
    for name, value in conninfo_to_dict(database_url).items():
        environment[environment_names.get(name, "PG" + name.upper())] = value
    result = subprocess.run(
        [executable, "--format=custom", "--no-owner", "--no-privileges", "--file", str(backup)],
        env=environment, capture_output=True, check=False,
    )
    if result.returncode or not backup.is_file() or backup.stat().st_size == 0:
        raise RuntimeError("数据库备份失败，未执行清理。请检查 pg_dump 版本、权限和连接配置。")
    return backup


def _retained_snapshot(connection) -> dict:
    """Check all surviving rows, excluding only explicitly retired columns."""
    result = {}
    for row in connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"):
        table = row["tablename"]
        if table in RETIRED_TABLES:
            continue
        projection = sql.SQL("md5((to_jsonb(t) - %s::text[])::text)")
        query = sql.SQL("SELECT count(*) AS rows, md5(coalesce(string_agg({0}, '' ORDER BY {0}), '')) AS digest FROM public.{1} t").format(projection, sql.Identifier(table))
        excluded = list(RETIRED_COLUMNS.get(table, ()))
        result[table] = dict(connection.execute(query, (excluded, excluded)).fetchone())
    return result


def cleanup_database(database_url: str, *, apply: bool = False,
                     backup_directory: Path = BACKUP_DIRECTORY, pg_dump: str | None = None) -> dict:
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        plan = inspect_database(connection)
    if not apply or not (plan["tables"] or plan["columns"] or plan["vector"]):
        return {"plan": plan, "applied": False, "backup": None}
    backup = _create_backup(database_url, backup_directory, pg_dump)
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10) as connection:
        connection.execute("SET LOCAL lock_timeout='5s'")
        connection.execute("SET LOCAL statement_timeout='60s'")
        tables = [row["tablename"] for row in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )]
        if tables:
            connection.execute(sql.SQL("LOCK TABLE {} IN SHARE MODE").format(
                sql.SQL(", ").join(sql.Identifier("public", table) for table in tables)
            ))
        before = _retained_snapshot(connection)
        connection.execute(SQL_FILE.read_text(encoding="utf-8"), prepare=False)
        remaining = inspect_database(connection)
        if remaining["tables"] or remaining["columns"] or remaining["vector"]:
            raise RuntimeError("清理后仍有停用对象，事务已回滚。")
        if _retained_snapshot(connection) != before:
            raise RuntimeError("保留数据校验不一致，事务已回滚。")
    return {"plan": plan, "applied": True, "backup": str(backup), "retained_tables": len(before)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="清理停用知识库、题库和固定教学内容；默认只预览")
    parser.add_argument("--apply", action="store_true", help="自动完整备份后执行事务清理")
    parser.add_argument("--backup-directory", type=Path, default=BACKUP_DIRECTORY)
    parser.add_argument("--pg-dump", help="pg_dump 可执行文件路径")
    args = parser.parse_args(argv)
    try:
        result = cleanup_database(Settings().database_url, apply=args.apply,
                                  backup_directory=args.backup_directory, pg_dump=args.pg_dump)
    except (psycopg.Error, RuntimeError, OSError) as error:
        # Upstream database/subprocess errors may contain connection details.
        print(f"清理失败（{type(error).__name__}）；未提交删除，请检查备份、依赖及数据库权限。", file=sys.stderr)
        return 1
    for table, count in result["plan"]["tables"].items():
        print(f"停用表：{table}（{count} 行）")
    for table, columns in result["plan"]["columns"].items():
        print(f"停用字段：{table}." + ", ".join(columns))
    if result["plan"]["vector"]:
        print("停用扩展：vector（若存在其他依赖会回滚）")
    if result["applied"]:
        print(f"备份：{result['backup']}")
        print(f"清理完成，{result['retained_tables']} 张保留表的数据校验通过。")
    elif args.apply:
        print("无需清理，数据库已无这些停用对象。")
    else:
        print("以上仅为预览，未修改数据库；使用 --apply 备份并执行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
