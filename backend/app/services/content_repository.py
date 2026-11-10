from __future__ import annotations

import json
from typing import Any
from app.core.exceptions import AppError
from app.schemas.content import Lesson, WorkedExample
from app.services.learning_repository import LearningRepository


class ContentError(AppError):
    status_code = 422
    code = 'CONTENT_INVALID'

class ContentNotReady(ContentError):
    status_code = 404
    code = 'CONTENT_NOT_READY'
    public_message = '未找到该教学内容。'

class ContentRepository:
    def __init__(self, repository: LearningRepository):
        self.repository = repository

    def _connect(self):
        return self.repository._connect()

    @staticmethod
    def dump(value):
        return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))

    def seed(self, payload: dict[str,Any]):
        for model, table, key in ((Lesson,'lessons','lessons'),(WorkedExample,'worked_examples','examples')):
            with self._connect() as c:
                for raw in payload[key]:
                    value=model.model_validate(raw)
                    self.repository.require_topic(value.topic_id)
                    old=c.execute(f'SELECT payload_json FROM {table} WHERE id=? AND version=?',(value.id,value.version)).fetchone()
                    serialized=self.dump(value.model_dump(mode='json'))
                    if old:
                        if old['payload_json'] != serialized:
                            raise ContentError('已存在内容版本不允许原地修改，请增加 version。')
                        continue
                    if table=='lessons':
                        c.execute('INSERT INTO lessons VALUES (?,?,?,?,?,?)',(value.id,value.version,value.topic_id,value.status,serialized,self.repository._now()))
                    else:
                        c.execute('INSERT INTO worked_examples VALUES (?,?,?,?,?,?,?)',(value.id,value.version,value.topic_id,value.family_id,value.status,serialized,self.repository._now()))
        return {'lessons': len(payload['lessons']), 'examples': len(payload['examples'])}

    def lesson(self, topic_id):
        self.repository.require_topic(topic_id)
        with self._connect() as c:
            row=c.execute("SELECT payload_json FROM lessons WHERE topic_id=? AND status='published' ORDER BY version DESC LIMIT 1",(topic_id,)).fetchone()
        if not row: raise ContentNotReady()
        return Lesson.model_validate_json(row['payload_json'])

    def examples(self, topic_id):
        self.repository.require_topic(topic_id)
        with self._connect() as c:
            rows=c.execute("SELECT e.payload_json FROM worked_examples e WHERE e.topic_id=? AND e.status='published' AND e.version=(SELECT MAX(x.version) FROM worked_examples x WHERE x.id=e.id AND x.status='published') ORDER BY e.id",(topic_id,)).fetchall()
        return [WorkedExample.model_validate_json(row['payload_json']) for row in rows]

    def example(self, example_id,version=None):
        with self._connect() as c:
            sql="SELECT payload_json FROM worked_examples WHERE id=? AND status='published'"
            args=[example_id]
            if version is not None: sql+=' AND version=?'; args.append(version)
            row=c.execute(sql+' ORDER BY version DESC LIMIT 1',args).fetchone()
        if not row: raise ContentNotReady()
        return WorkedExample.model_validate_json(row['payload_json'])

    def exposure(self,student_id,content_id,version,family_id,kind,assessment_id=None):
        with self._connect() as c:
            c.execute('INSERT INTO content_exposures(student_id,content_id,content_version,family_id,kind,assessment_id,created_at) VALUES (?,?,?,?,?,?,?)',(student_id,content_id,version,family_id,kind,assessment_id,self.repository._now()))

    def coverage(self):
        with self._connect() as c:
            topics=c.execute('SELECT id,title,course,required_dimensions_json FROM curriculum_topics WHERE active=1 ORDER BY course,stage,order_index').fetchall()
            ls=c.execute("SELECT topic_id,COUNT(DISTINCT id) n FROM lessons WHERE status='published' GROUP BY topic_id").fetchall()
            es=c.execute("SELECT topic_id,COUNT(DISTINCT id) n FROM worked_examples WHERE status='published' GROUP BY topic_id").fetchall()
        lc={r['topic_id']:r['n'] for r in ls}; ec={r['topic_id']:r['n'] for r in es}
        out=[]
        for topic in topics:
            topic_id=topic['id']
            gaps=[]
            if lc.get(topic_id,0)<1: gaps.append('缺少已发布讲解')
            if ec.get(topic_id,0)<2: gaps.append('完整例题不足 2 道')
            out.append({'topic_id':topic_id,'title':topic['title'],'owner_course':topic['course'],
                'lesson_count':lc.get(topic_id,0),'example_count':ec.get(topic_id,0),
                'local_flow_ready':not gaps,
                'has_learning_content':bool(lc.get(topic_id,0) or ec.get(topic_id,0)),
                'readiness_gaps':gaps})
        byid={t['topic_id']:t for t in out}
        topic_ids=[topic['id'] for topic in topics]
        with self._connect() as c:
            prerequisite_rows=c.execute("""SELECT p.id,p.title,tp.topic_id,tp.relation_type,tp.scope
                FROM topic_prerequisites tp JOIN curriculum_topics p ON p.id=tp.prerequisite_topic_id
                WHERE tp.topic_id = ANY(?) AND tp.relation_type='required' AND tp.scope='topic'
                ORDER BY p.order_index""",(topic_ids,)).fetchall()
        dependencies={topic_id:[] for topic_id in topic_ids}
        for row in prerequisite_rows:
            dependencies[row['topic_id']].append(dict(row))
        memo={}
        def ready(tid,seen):
            if tid in seen: return False
            if tid in memo: return memo[tid]
            row=byid.get(tid,{})
            value=bool(row.get('local_flow_ready')) and all(ready(p['id'],seen|{tid}) for p in dependencies.get(tid,[]))
            memo[tid]=value
            return value
        for row in out:
            unmet=[p for p in dependencies[row['topic_id']] if not ready(p['id'],set())]
            row['prerequisites_ready']=not unmet
            row['full_flow_ready']=ready(row['topic_id'],set())
            if unmet:
                row['readiness_gaps'].append('前置内容待补充：'+'、'.join(p['title'] for p in unmet))
        return {'topics':out}
