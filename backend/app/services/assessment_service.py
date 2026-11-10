"""Persisted dynamic assessments and local prerequisite verification."""
from __future__ import annotations

import json
from app.core.exceptions import PracticeSetNotFoundError
from app.services.content_repository import ContentError

RULE_VERSION='content-v1'

def evidence_allowed(repository,assessment_id):
    with repository._connect() as c:
        row=c.execute('SELECT purpose FROM practice_sets WHERE id=?',(assessment_id,)).fetchone()
        if not row or row['purpose']=='legacy': return True
        if row['purpose']=='prerequisite_test': return False
        invalid=c.execute('SELECT COUNT(*) FROM practice_questions WHERE practice_set_id=? AND (used_hint=1 OR solution_revealed=1 OR evidence_eligible=0 OR attempt_count>0)',(assessment_id,)).fetchone()["count"]
        invalid+=c.execute("SELECT COUNT(*) FROM practice_questions q JOIN practice_sets ps ON ps.id=q.practice_set_id WHERE ps.id=? AND EXISTS (SELECT 1 FROM content_exposures e WHERE e.student_id=ps.student_id AND e.family_id=q.family_id AND e.kind IN ('example','solution','hint','feedback') AND (e.assessment_id IS NULL OR e.assessment_id<>ps.id))",(assessment_id,)).fetchone()["count"]
    return invalid==0

class AssessmentService:
    def __init__(self, repository, settings):
        self.repository = repository
        self.settings = settings

    def get(self,student_id,assessment_id):
        self.repository.require_student(student_id)
        internal=self.repository.get_practice_set_internal(assessment_id,student_id=student_id)
        with self.repository._connect() as c:
            row=c.execute('SELECT purpose,status FROM practice_sets WHERE id=?',(assessment_id,)).fetchone()
            result=c.execute('SELECT response_json FROM practice_submissions WHERE practice_set_id=? AND student_id=? AND response_json IS NOT NULL ORDER BY created_at DESC LIMIT 1',(assessment_id,student_id)).fetchone()
        return {'id':assessment_id,'practice_set_id':assessment_id,'topic_id':internal.topic_id,
            'mode':internal.kind,'purpose':row['purpose'],'status':row['status'],
            'questions':[q.to_public().model_dump(mode='json') for q in internal.questions],
            'source_summary':[{'source_id':s.source_id,'source_file':s.source_file,'title':s.title} for s in internal.source_snapshot],
            'result':json.loads(result['response_json']) if result else None}

    def prerequisite_target(self,student_id,payload):
        self.repository.require_student(student_id)
        self.repository.require_topic(payload.topic_id)
        unmet=self.repository.get_unmet_prerequisites(student_id,payload.topic_id)
        target=next((p for p in unmet if not payload.prerequisite_topic_id or p['id']==payload.prerequisite_topic_id),None)
        if not target: raise ContentError('没有对应的未满足正式前置要求，请返回知识点查看最新状态。')
        competencies=target.get('required_competencies') or [target['id']+'.foundation']
        return target,competencies

    def after_submit(self,student_id,assessment_id,response):
        with self.repository._connect() as c:
            row=c.execute('SELECT purpose,prerequisite_for,topic_id,rule_version FROM practice_sets WHERE id=? AND student_id=?',(assessment_id,student_id)).fetchone()
            if not row: raise PracticeSetNotFoundError()
            if row['purpose']!='prerequisite_test' or response.status!='evaluated' or response.total_score<80: return
            qs=c.execute('SELECT id,competencies_json,attempt_count,evidence_eligible,used_hint,solution_revealed FROM practice_questions WHERE practice_set_id=?',(assessment_id,)).fetchall()
            if any(q['attempt_count']!=1 or not q['evidence_eligible'] or q['used_hint'] or q['solution_revealed'] for q in qs): return
            scores={e.question_id:e for e in response.evaluations}
            competencies={k for q in qs for k in json.loads(q['competencies_json'])}
            for competency in competencies:
                covered=[scores[q['id']] for q in qs if competency in json.loads(q['competencies_json'])]
                if not covered or not all(e.evaluation_reliable for e in covered) or sum(e.score for e in covered)/len(covered)<80: continue
                c.execute('INSERT INTO prerequisite_verifications(student_id,dependent_topic_id,prerequisite_topic_id,competency,rule_version,assessment_id,verified_at) VALUES (?,?,?,?,?,?,?) ON CONFLICT(student_id,dependent_topic_id,prerequisite_topic_id,competency,rule_version) DO NOTHING',
                    (student_id,row['prerequisite_for'],row['topic_id'],competency,row['rule_version'],assessment_id,self.repository._now()))
