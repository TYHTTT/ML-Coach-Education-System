"""Validate bundled lessons and worked examples without importing questions."""
from __future__ import annotations
import argparse
import json
from app.content.seeds.core import build_content, verify_content
from app.schemas.content import Lesson, WorkedExample


def main(argv=None):
    parser=argparse.ArgumentParser(description='校验课程讲解、教学例题和可信数值计算')
    parser.parse_args(argv)
    payload=build_content()
    for key,model in [('lessons',Lesson),('examples',WorkedExample)]:
        for value in payload[key]: model.model_validate(value)
    errors=verify_content(payload)
    print(json.dumps({'counts':{k:len(v) for k,v in payload.items()},'errors':errors},ensure_ascii=False))
    return 1 if errors else 0


if __name__=='__main__': raise SystemExit(main())
