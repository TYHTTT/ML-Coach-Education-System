"""Saved teaching examples are independent of removed bank management."""
import json
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.content.seeds.core import build_content
from app.services.content_repository import ContentRepository
from app.services.evaluation_service import score_numeric

_tokens={}

class NoNetworkLLM:
    def __init__(self):self.calls=[]
    async def generate(self,messages,temperature=None):
        self.calls.append(messages)
        return '根据保存例题，这一步使用内积定义逐项相乘并求和。'

@pytest.fixture
def content_app(settings):
    llm=NoNetworkLLM()
    app=create_app(settings,llm_client=llm,)
    with TestClient(app) as client:
        repo=app.state.learning_repository
        content=ContentRepository(repo);content.seed(build_content())
        account=repo.register_student(username='teaching_test',display_name='测试学生',password='test-password')
        sid=account['id']; _tokens[sid]=account['access_token']
        yield client,repo,content,sid,llm,settings

def headers(sid):return {'Authorization':'Bearer '+_tokens[sid]}

def test_saved_lessons_are_stable_and_bank_routes_are_gone(content_app):
    client,repo,content,sid,llm,_=content_app
    first=client.get('/api/v1/topics/ml.linear_regression/lesson')
    assert first.status_code == 200
    assert client.get('/api/v1/topics/ml.linear_regression/lesson').json() == first.json()
    assert first.json()['practice_recommendations'] == []
    assert not llm.calls


def test_example_ask_uses_saved_version_and_does_not_increase_mastery(content_app):
    client,repo,content,sid,llm,_=content_app
    value=content.examples('la.dot_product')[0]
    path=f'/api/v1/examples/{value.id}'
    assert client.post(path+'/exposure',headers=headers(sid),json={'version':value.version}).json()['mastery_updated'] is False
    asked=client.post(path+'/ask',headers=headers(sid),json={'version':value.version,'step_id':value.steps[0].step_id,'question':'解释这个步骤'})
    assert asked.status_code==200
    data=json.loads(llm.calls[-1][-1]['content'])
    assert data['selected_step']==value.steps[0].model_dump()
    assert data['version']==value.version
    assert repo.get_topic_state(sid,'la.dot_product') is None
    assert client.post(path+'/ask',headers=headers(sid),json={'version':999,'step_id':'fake'}).status_code==404

@pytest.mark.parametrize('answer,expected',[('1.2e3 m',True),('1200',True),('NaN m',False),('Infinity',False),('__import__("os")',False),('1200 kg',False)])
def test_numeric_units_scientific_and_unsafe_input(answer,expected):
    assert score_numeric(answer,1200,0.01,['m'])==(100.0,True) if expected else score_numeric(answer,1200,0.01,['m'])[1] is False
