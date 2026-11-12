"""Add administrator accounts to an existing database without changing student data."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings
from app.db.database import PostgresDatabase


def main() -> int:
    try:
        with PostgresDatabase(Settings().database_url).connect() as connection:
            connection.execute_script(Path(__file__).with_suffix(".sql").read_text(encoding="utf-8"))
    except Exception as error:
        print(f"管理员表创建失败（{type(error).__name__}），请检查数据库连接和权限。", file=sys.stderr)
        return 1
    print("管理员表已就绪，已有学生账户和学习数据保持不变。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
