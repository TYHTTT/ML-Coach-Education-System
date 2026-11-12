"""Back up and remove retired prerequisite settings from an existing database."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings
from cleanup_retired import _create_backup

SQL_FILE = Path(__file__).with_suffix(".sql")
RETIRED_TABLES = {"topic_prerequisites", "prerequisite_verifications"}
RETIRED_COLUMNS = ["prerequisite_for", "rule_version"]


def inspect(connection):
    tables = [row["tablename"] for row in connection.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )]
    columns = [row["column_name"] for row in connection.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' "
        "AND table_name='practice_sets' AND column_name=ANY(%s) ORDER BY column_name", (RETIRED_COLUMNS,)
    )]
    locked = connection.execute("SELECT count(*) AS n FROM student_topic_states WHERE status='locked'").fetchone()["n"]
    return {"tables": sorted(RETIRED_TABLES.intersection(tables)), "columns": columns, "locked_states": locked}


def retained_snapshot(connection):
    """Compare every surviving row, allowing only the declared status conversion."""
    result = {}
    for row in connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"):
        table = row["tablename"]
        if table in RETIRED_TABLES:
            continue
        projection = sql.SQL("to_jsonb(t)")
        if table == "practice_sets":
            projection = sql.SQL("to_jsonb(t) - ARRAY['prerequisite_for','rule_version']::text[]")
        elif table == "student_topic_states":
            projection = sql.SQL("to_jsonb(t) || jsonb_build_object('status',CASE WHEN status='locked' THEN 'not_started' ELSE status END)")
        query = sql.SQL("SELECT count(*) AS rows, md5(coalesce(string_agg(md5(({0})::text),'' ORDER BY md5(({0})::text)),'')) AS digest FROM public.{1} t").format(projection, sql.Identifier(table))
        result[table] = dict(connection.execute(query).fetchone())
    return result


def remove_prerequisites(database_url, *, apply=False, backup_directory=None, pg_dump=None):
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        plan = inspect(connection)
    if not apply:
        return {"plan": plan, "applied": False, "backup": None}
    backup = _create_backup(database_url, backup_directory or SQL_FILE.parent / "backups", pg_dump)
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10) as connection:
        connection.execute("SET LOCAL lock_timeout='5s'")
        connection.execute("SET LOCAL statement_timeout='60s'")
        tables = [row["tablename"] for row in connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
        connection.execute(sql.SQL("LOCK TABLE {} IN SHARE MODE").format(sql.SQL(",").join(sql.Identifier(t) for t in tables)))
        before = retained_snapshot(connection)
        connection.execute(SQL_FILE.read_text(encoding="utf-8"), prepare=False)
        if before != retained_snapshot(connection):
            raise RuntimeError("保留数据校验失败，迁移已回滚。")
        if any(inspect(connection).values()):
            raise RuntimeError("前置设定仍有残留，迁移已回滚。")
    return {"plan": plan, "applied": True, "backup": str(backup), "retained_tables": len(before)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="备份后执行清理；默认只检查")
    parser.add_argument("--pg-dump", help="pg_dump 可执行文件路径")
    args = parser.parse_args()
    try:
        result = remove_prerequisites(Settings().database_url, apply=args.apply, pg_dump=args.pg_dump)
    except Exception as error:
        print(f"前置设定清理失败（{type(error).__name__}），数据库事务已回滚。", file=sys.stderr)
        return 1
    if result["applied"]:
        print(f"前置设定已清理；备份已保存，{result['retained_tables']} 张保留表的数据校验通过。")
    else:
        print(f"待清理关系表 {len(result['plan']['tables'])} 张，字段 {len(result['plan']['columns'])} 个，锁定状态 {result['plan']['locked_states']} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
