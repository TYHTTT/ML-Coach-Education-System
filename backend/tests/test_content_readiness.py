"""Course readiness depends on teaching content and prerequisite content."""
from app.services.content_repository import ContentRepository


class Rows(list):
    def fetchall(self): return self


class Database:
    def __init__(self, examples=2): self.examples=examples; self.queries=[]
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, query, params=()):
        self.queries.append(query)
        assert 'question_bank' not in query
        if 'FROM curriculum_topics' in query:
            return Rows([{'id':'la.vectors','title':'向量','course':'linear_algebra'},
                         {'id':'ml.linear_regression','title':'线性回归','course':'machine_learning'}])
        if 'FROM lessons' in query: return Rows([{'topic_id':'la.vectors','n':1},{'topic_id':'ml.linear_regression','n':1}])
        if 'FROM worked_examples' in query: return Rows([{'topic_id':'la.vectors','n':self.examples},{'topic_id':'ml.linear_regression','n':2}])
        if 'FROM topic_prerequisites' in query: return Rows([{'id':'la.vectors','title':'向量','topic_id':'ml.linear_regression','relation_type':'required','scope':'topic'}])
        raise AssertionError(query)


class Repository:
    def __init__(self, examples=2): self.database=Database(examples)
    def _connect(self): return self.database


def test_teaching_content_can_be_ready_without_a_question_inventory():
    rows=ContentRepository(Repository()).coverage()['topics']
    assert all(row['full_flow_ready'] for row in rows)
    assert all('practice_count' not in row and 'checkpoint_count' not in row for row in rows)


def test_missing_prerequisite_teaching_content_still_marks_dependent_topic_missing():
    rows={row['topic_id']:row for row in ContentRepository(Repository(examples=1)).coverage()['topics']}
    assert not rows['la.vectors']['full_flow_ready']
    assert not rows['ml.linear_regression']['prerequisites_ready']
    assert rows['ml.linear_regression']['has_learning_content']
    assert any('前置内容待补充' in gap for gap in rows['ml.linear_regression']['readiness_gaps'])
