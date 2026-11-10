"""Trusted arithmetic and teaching content remain available without a bank."""
import json
import math
from pathlib import Path
import pytest
from app.content.seeds.core import TOPICS, build_content, calculate, verify_content
from app.schemas.content import Lesson, WorkedExample


def _example(suffix):
    return next(e for e in build_content()["examples"] if e["id"].endswith(suffix))


def test_required_example_a_linear_regression_training_step():
    """Independently compute every requested A value from the original data."""
    xs, ys, w, b, eta = [1, 2], [2, 4], 1, 0, 0.1
    predictions = [w*x+b for x in xs]
    residuals = [p-y for p,y in zip(predictions,ys,strict=True)]
    loss = sum(r*r for r in residuals) / (2*len(xs))
    dw = sum(r*x for r,x in zip(residuals,xs,strict=True)) / len(xs)
    db = sum(residuals) / len(xs)
    next_w, next_b = w-eta*dw, b-eta*db
    next_loss = sum((next_w*x+next_b-y)**2 for x,y in zip(xs,ys,strict=True)) / (2*len(xs))
    assert predictions == [1,2]
    assert (loss,dw,db,next_w,next_b,next_loss) == pytest.approx((1.25,-2.5,-1.5,1.25,0.15,0.545625))
    example = _example("A_training_step")
    assert example["givens"]["normalization"] == "1/(2n)"
    assert "0.545625" in example["final_answer"]
    assert len(example["steps"]) >= 5


def test_required_example_b_partial_derivatives_and_gradient():
    x,y = 1,2
    gradient = (2*x,6*y)
    function_value = x*x+3*y*y
    assert gradient == (2,12)
    assert function_value == 13
    example = _example("B_partial_gradient")
    assert "(2,12)" in example["final_answer"]
    assert "13" in example["final_answer"]


def test_required_example_c_dot_bias_sigmoid():
    x,w,b = (2,1),(0.5,-1),0.5
    dot = sum(a*c for a,c in zip(x,w,strict=True))
    z = dot+b
    probability = 1/(1+math.exp(-z))
    assert dot == 0
    assert z == 0.5
    assert probability == pytest.approx(0.6224593312018546)
    assert "0.622459" in _example("C_dot_sigmoid")["final_answer"]


def test_required_example_d_conditional_probability():
    joint, condition = 0.2,0.5
    assert 0 <= joint <= condition <= 1
    assert joint/condition == pytest.approx(0.4)
    assert "0.4" in _example("D_conditional")["final_answer"]


def test_required_example_e_binary_cross_entropy():
    y,p = 1,0.8
    loss = -(y*math.log(p)+(1-y)*math.log(1-p))
    assert loss == pytest.approx(0.2231435513142097)
    assert loss < -math.log(0.4)
    assert "0.223144" in _example("E_positive_label")["final_answer"]


def _curriculum_topics():
    seed_path = Path(__file__).resolve().parents[1]/"app"/"curriculum"/"seeds"
    topics = {}
    for name in ("machine_learning.json","advanced_mathematics.json"):
        topics.update({t["id"]:t for t in json.loads((seed_path/name).read_text(encoding="utf-8"))["topics"]})
    config = json.loads((seed_path/"content_curriculum.json").read_text(encoding="utf-8"))
    for course in config["additional_courses"]:
        topics.update({t["id"]:t for t in course["topics"]})
    return topics,config


def test_required_core_prerequisite_closure_is_not_empty():
    data=build_content()
    _,config=_curriculum_topics()
    available={l["topic_id"] for l in data["lessons"]}
    required=set()
    pending=list(available)
    while pending:
        target=pending.pop()
        for relation in config["relations"].get(target,[]):
            if relation.get("relation_type","required")!="required" or relation.get("scope","topic")!="topic":
                continue
            prerequisite=relation.get("topic_id",relation.get("prerequisite_topic_id"))
            if prerequisite not in required:
                required.add(prerequisite)
                pending.append(prerequisite)
    assert required <= available
    for topic_id in required:
        assert any(example['topic_id']==topic_id for example in data['examples'])



def test_calculations_do_not_execute_unregistered_operations():
    with pytest.raises(ValueError,match="Unregistered"):
        calculate("__import__('os').system('anything')",[])


def test_all_teaching_payloads_pass_schemas_without_fixed_questions():
    content=build_content()
    assert set(content) == {"lessons", "examples"}
    for raw in content["lessons"]:
        value=Lesson.model_validate(raw)
        assert value.version == 2
        assert value.practice_recommendations == []
    for raw in content["examples"]:
        value=WorkedExample.model_validate(raw)
        assert value.version == 2
        assert value.followup_practice_ids == []
    assert verify_content(content) == []


@pytest.mark.parametrize("topic_id", list(TOPICS))
def test_each_core_unit_has_real_lessons_and_worked_examples(topic_id):
    content=build_content()
    assert len([x for x in content["lessons"] if x["topic_id"] == topic_id]) == 1
    examples=[x for x in content["examples"] if x["topic_id"] == topic_id]
    assert len(examples) >= 2
    assert all(len(x["steps"]) >= 3 for x in examples)


def test_worked_calculation_verifier_detects_tampered_answer():
    content=build_content()
    content["examples"][0]["verification"]["checks"][0]["expected"] = -99999
    assert any("worked calculation mismatch" in error for error in verify_content(content))
