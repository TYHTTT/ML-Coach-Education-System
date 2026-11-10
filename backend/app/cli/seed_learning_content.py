from __future__ import annotations
import argparse
import json
from app.core.config import Settings
from app.curriculum.seed import seed_curriculum
from app.services.learning_repository import LearningRepository
from app.services.content_repository import ContentRepository
from app.content.seeds.core import build_content, verify_content

def main(argv=None):
    parser=argparse.ArgumentParser(description='幂等导入已版本化教学内容；绝不清空现有表')
    parser.add_argument('--database-url')
    args=parser.parse_args(argv)
    errors=verify_content()
    if errors:
        print(json.dumps({'verification_errors':errors},ensure_ascii=False));return 1
    repo=LearningRepository(args.database_url or Settings().database_url)
    seed_curriculum(repo)
    content=ContentRepository(repo)
    print(json.dumps(content.seed(build_content()),ensure_ascii=False))
    rows=content.coverage()['topics']
    print(json.dumps({'ready_topics':sum(r['full_flow_ready'] for r in rows),'total_topics':len(rows)},ensure_ascii=False))
    return 0

if __name__=='__main__': raise SystemExit(main())
