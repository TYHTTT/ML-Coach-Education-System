"""Add related-topic edges without modifying course layouts or learning records."""
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


def enable_topic_relations(database_url, *, backup_directory=None, pg_dump=None):
    backup = _create_backup(database_url, backup_directory or SQL_FILE.parent / "backups", pg_dump)
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10) as connection:
        connection.execute("SET LOCAL lock_timeout='5s'")
        connection.execute("SET LOCAL statement_timeout='60s'")
        tables = [row["tablename"] for row in connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
        connection.execute(sql.SQL("LOCK TABLE {} IN SHARE MODE").format(sql.SQL(",").join(sql.Identifier(t) for t in tables)))
        before = _retained_snapshot(connection)
        connection.execute(SQL_FILE.read_text(encoding="utf-8"), prepare=False)
        after = _retained_snapshot(connection)
        if before != {name: after[name] for name in before}:
            raise RuntimeError("既有数据校验失败，迁移已回滚。")
    return {"backup": str(backup), "retained_tables": len(before)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-dump")
    args = parser.parse_args()
    try:
        result = enable_topic_relations(Settings().database_url, pg_dump=args.pg_dump)
    except Exception as error:
        print(f"知识点关联迁移失败（{type(error).__name__}），事务已回滚。", file=sys.stderr)
        return 1
    print(f"知识点关联表已启用；备份已保存，{result['retained_tables']} 张既有表数据校验通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
