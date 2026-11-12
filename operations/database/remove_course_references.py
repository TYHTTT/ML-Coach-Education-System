"""Back up and remove cross-course knowledge point placements and their flag."""
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


def inspect(connection):
    count = connection.execute("SELECT count(*) AS n FROM topic_placements p JOIN curriculum_topics t ON t.id=p.topic_id WHERE t.course<>p.course_id").fetchone()["n"]
    column = bool(connection.execute("SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='topic_placements' AND column_name='is_reference'").fetchone())
    constraint = bool(connection.execute("SELECT 1 FROM pg_constraint WHERE conrelid='public.topic_placements'::regclass AND conname='topic_placements_topic_course_fkey' AND convalidated").fetchone())
    return {"pending": count, "reference_column": column, "ownership_constraint": constraint}


def snapshot(connection):
    result = _retained_snapshot(connection)
    result["topic_placements"] = dict(connection.execute("""SELECT count(*) AS rows,
        md5(coalesce(string_agg(md5((to_jsonb(p)-'is_reference')::text),'' ORDER BY md5((to_jsonb(p)-'is_reference')::text)),'')) AS digest
        FROM public.topic_placements p JOIN public.curriculum_topics t ON t.id=p.topic_id WHERE t.course=p.course_id""").fetchone())
    return result


def remove_course_references(database_url, *, apply=False, backup_directory=None, pg_dump=None):
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        plan = inspect(connection)
    if not apply or (not plan["pending"] and not plan["reference_column"] and plan["ownership_constraint"]):
        return {"applied": False, "plan": plan, "backup": None}
    backup = _create_backup(database_url, backup_directory or SQL_FILE.parent / "backups", pg_dump)
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10) as connection:
        connection.execute("SET LOCAL lock_timeout='5s'")
        connection.execute("SET LOCAL statement_timeout='60s'")
        tables = [row["tablename"] for row in connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
        connection.execute(sql.SQL("LOCK TABLE {} IN SHARE MODE").format(sql.SQL(",").join(sql.Identifier(t) for t in tables)))
        before = snapshot(connection)
        connection.execute(SQL_FILE.read_text(encoding="utf-8"), prepare=False)
        remaining = inspect(connection)
        if remaining["pending"] or remaining["reference_column"] or not remaining["ownership_constraint"] or before != snapshot(connection):
            raise RuntimeError("保留数据或知识点归属校验失败，迁移已回滚。")
    return {"applied": True, "plan": plan, "backup": str(backup), "retained_tables": len(before)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--pg-dump")
    args = parser.parse_args()
    try:
        result = remove_course_references(Settings().database_url, apply=args.apply, pg_dump=args.pg_dump)
    except Exception as error:
        print(f"跨课程引用清理失败（{type(error).__name__}），事务已回滚。", file=sys.stderr)
        return 1
    if result["applied"]:
        print(f"跨课程引用已清理，引用标记已删除，归属约束已启用；备份已保存，{result['retained_tables']} 张保留表校验通过。")
    else:
        print(f"待移除引用 {result['plan']['pending']} 条，引用标记存在：{result['plan']['reference_column']}，归属约束已启用：{result['plan']['ownership_constraint']}。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
