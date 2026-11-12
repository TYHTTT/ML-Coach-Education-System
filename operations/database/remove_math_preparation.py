"""Remove legacy mathematics-preparation placements after backing up the database."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings
from cleanup_retired import _create_backup, _retained_snapshot

SQL_FILE = Path(__file__).with_suffix(".sql")
TARGET = "course_id='machine_learning' AND is_reference=1 AND parent_group_id ~ '^math-preparation-'"


def snapshot(connection):
    result = _retained_snapshot(connection)
    result["topic_placements"] = dict(connection.execute(
        "SELECT count(*) AS rows, md5(coalesce(string_agg(md5(to_jsonb(t)::text),'' ORDER BY md5(to_jsonb(t)::text)),'')) AS digest "
        "FROM public.topic_placements t WHERE NOT (" + TARGET + ")"
    ).fetchone())
    return result


def remove_math_preparation(database_url, *, apply=False, backup_directory=None, pg_dump=None):
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        count = connection.execute("SELECT count(*) AS n FROM topic_placements WHERE " + TARGET).fetchone()["n"]
    if not apply or not count:
        return {"applied": False, "removed": 0, "pending": count, "backup": None}
    backup = _create_backup(database_url, backup_directory or SQL_FILE.parent / "backups", pg_dump)
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10) as connection:
        connection.execute("SET LOCAL lock_timeout='5s'")
        connection.execute("SET LOCAL statement_timeout='60s'")
        tables = [row["tablename"] for row in connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
        connection.execute(sql.SQL("LOCK TABLE {} IN SHARE MODE").format(sql.SQL(",").join(sql.Identifier(t) for t in tables)))
        before = snapshot(connection)
        removed = connection.execute(SQL_FILE.read_text(encoding="utf-8"), prepare=False).rowcount
        remaining = connection.execute("SELECT count(*) AS n FROM topic_placements WHERE " + TARGET).fetchone()["n"]
        if remaining or before != snapshot(connection):
            raise RuntimeError("保留数据校验失败，迁移已回滚。")
    return {"applied": True, "removed": removed, "pending": 0, "backup": str(backup)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--pg-dump")
    args = parser.parse_args()
    try:
        result = remove_math_preparation(Settings().database_url, apply=args.apply, pg_dump=args.pg_dump)
    except Exception as error:
        print(f"数学准备清理失败（{type(error).__name__}），数据库事务已回滚。", file=sys.stderr)
        return 1
    if result["applied"]:
        print(f"已移除 {result['removed']} 条数学准备目录引用；备份已保存，独立课程和学习记录校验通过。")
    else:
        print(f"待移除数学准备目录引用 {result['pending']} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
