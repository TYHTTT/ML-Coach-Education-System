"""Allow administrators to compile inactive courses without touching learning data."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import Settings
from app.db.database import PostgresDatabase


def main():
    try:
        with PostgresDatabase(Settings().database_url).connect() as connection:
            connection.execute_script(Path(__file__).with_suffix(".sql").read_text(encoding="utf-8"))
    except Exception as error:
        print(f"知识点编排迁移失败（{type(error).__name__}），事务已回滚。", file=sys.stderr)
        return 1
    print("知识点编排数据库迁移完成，已有知识点和学习数据保持不变。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
