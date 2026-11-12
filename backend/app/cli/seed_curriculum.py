from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.core.config import Settings
from app.curriculum.seed import seed_curriculum
from app.services.learning_repository import LearningRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导入 Course Coach 默认课程知识点")
    parser.add_argument("--database-url", help="覆盖配置中的 PostgreSQL DATABASE_URL")
    parser.add_argument(
        "--seed",
        action="append",
        type=Path,
        help="自定义 Seed JSON；可重复传入。省略时导入四门课程目录",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = LearningRepository(args.database_url or Settings().database_url)
    try:
        counts = seed_curriculum(repository, args.seed)
    except Exception as exc:
        print(f"Seed 导入失败：{exc}", file=sys.stderr)
        return 1
    summary = "，".join(f"{course} {count} 个" for course, count in counts.items())
    print(f"课程 Seed 导入完成：{summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
