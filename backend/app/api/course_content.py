"""Stable canonical curriculum navigation and prerequisite explanations."""
from __future__ import annotations

from fastapi import APIRouter, Header, Request, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.types import Course
from app.services.learning_service import LearningService
from app.api.dependencies import agent_from_request, student_id_from_authorization
from app.schemas.chat import ChatResponse

router = APIRouter(prefix="/api/v1", tags=["course-content"])


def _can_checkpoint(request: Request, student_id: str | None, topic: dict) -> bool:
    if student_id is None:
        return False
    repository = request.app.state.learning_repository
    if repository.get_unmet_prerequisites(student_id, topic["id"]):
        return False
    state = repository.get_topic_state(student_id, topic["id"])
    service = LearningService(settings=request.app.state.settings, repository=repository)
    gate = service.evaluate_topic_gate(student_id, topic, state)
    return bool(gate.next_action == "take_checkpoint" or (state and state["status"] in ("ready_for_checkpoint", "mastered")))


@router.get("/courses")
def registered_courses(request: Request):
    with request.app.state.learning_repository._connect() as connection:
        return {"courses": [dict(row) for row in connection.execute("SELECT * FROM courses WHERE active=1 ORDER BY id")]}


@router.get("/courses/{course}/outline")
def outline(course: Course, request: Request, authorization: str | None = Header(default=None, alias="Authorization")):
    repository = request.app.state.learning_repository
    student_id = student_id_from_authorization(authorization, repository)
    with repository._connect() as connection:
        placements = [dict(row) for row in connection.execute("""SELECT p.*,t.title,t.description,t.course AS owner_course
            FROM topic_placements p JOIN curriculum_topics t ON t.id=p.topic_id
            WHERE p.course_id=? AND t.active=1 ORDER BY p.is_reference DESC,p.order_index""", (course.value,))]
        topic_ids = [placement["topic_id"] for placement in placements]
        topics = {
            row["id"]: repository._topic_record(row)
            for row in connection.execute(
                "SELECT * FROM curriculum_topics WHERE id = ANY(?)", (topic_ids,)
            )
        }
        states = {}
        if student_id:
            states = {
                row["topic_id"]: dict(row)
                for row in connection.execute(
                    "SELECT * FROM student_topic_states WHERE student_id=? AND topic_id = ANY(?)",
                    (student_id, topic_ids),
                )
            }
        prerequisite_rows = [dict(row) for row in connection.execute(
            """SELECT p.id,p.slug,p.title,p.course,tp.topic_id,tp.prerequisite_topic_id,
                tp.required_mastery,tp.relation_type,tp.reason,tp.required_competencies_json,
                tp.scope,tp.section_id,tp.rule_version
                FROM topic_prerequisites tp JOIN curriculum_topics p ON p.id=tp.prerequisite_topic_id
                WHERE tp.topic_id = ANY(?) ORDER BY p.order_index""",
            (topic_ids,),
        )]
        prerequisite_states = {}
        verified_competencies: dict[tuple[str, str], set[str]] = {}
        if student_id:
            prerequisite_ids = list({row["prerequisite_topic_id"] for row in prerequisite_rows})
            if prerequisite_ids:
                prerequisite_states = {
                    row["topic_id"]: dict(row)
                    for row in connection.execute(
                        "SELECT * FROM student_topic_states WHERE student_id=? AND topic_id = ANY(?)",
                        (student_id, prerequisite_ids),
                    )
                }
                for row in connection.execute(
                    """SELECT prerequisite_topic_id,rule_version,competency FROM prerequisite_verifications
                        WHERE student_id=? AND prerequisite_topic_id = ANY(?)""",
                    (student_id, prerequisite_ids),
                ):
                    verified_competencies.setdefault(
                        (row["prerequisite_topic_id"], row["rule_version"]), set()
                    ).add(row["competency"])
    prerequisites: dict[str, list[dict]] = {}
    for row in prerequisite_rows:
        topic_id = row.pop("topic_id")
        row["dependent_topic_id"] = topic_id
        row["required_competencies"] = repository._load_json(row.pop("required_competencies_json"), [])
        prerequisites.setdefault(topic_id, []).append(row)
    groups: dict[str, dict] = {}
    if any(item["is_reference"] for item in placements):
        groups["math-preparation"] = {"id":"math-preparation","title":"数学准备","parent_group_id":None,"order_index":0,"topics":[]}
    recommended = None
    for placement in placements:
        topic_id = placement["topic_id"]
        topic = topics[topic_id]
        state = states.get(topic_id)
        unmet = []
        for edge in prerequisites.get(topic_id, []):
            if edge["relation_type"] != "required" or edge["scope"] != "topic":
                continue
            if not student_id:
                unmet.append(edge)
                continue
            prerequisite_state = prerequisite_states.get(edge["id"])
            verified = verified_competencies.get((edge["id"], edge["rule_version"]), set())
            required_competencies = set(edge["required_competencies"])
            satisfied = bool(
                prerequisite_state
                and prerequisite_state["status"] == "mastered"
                and prerequisite_state["mastery"] >= edge["required_mastery"]
            ) or bool(required_competencies and required_competencies <= verified)
            if not satisfied:
                unmet.append(edge)
        group_id = placement["parent_group_id"]
        group = groups.setdefault(group_id, {"id":group_id,"title":placement["group_title"],"parent_group_id":"math-preparation" if placement["is_reference"] else None,"order_index":len(groups),"topics":[]})
        status = state["status"] if state and state["status"]!="locked" else "not_started"
        group["topics"].append({"id":topic_id,"topic_id":topic_id,"owner_course":placement["owner_course"],
            "title":topic["title"],"description":topic["description"],"learning_objectives":topic["learning_objectives"],
            "order_index":placement["order_index"],"is_reference":bool(placement["is_reference"]),"status":status,
            "mastery":float(state["mastery"]) if state and state["evidence_count"] else None,
            "prerequisite_gap":[{"id":edge["id"],"title":edge["title"],"reason":edge["reason"]} for edge in unmet]})
        if recommended is None and status!="mastered" and not unmet:
            recommended = topic_id
    return {"course":course.value,"title":course.display_name,"groups":list(groups.values()),"recommended_topic_id":recommended}


@router.get("/topics/{topic_id}/prerequisites")
def prerequisites(topic_id: str, request: Request, authorization: str | None = Header(default=None, alias="Authorization")):
    repository = request.app.state.learning_repository
    student_id = student_id_from_authorization(authorization, repository)
    topic = repository.require_topic(topic_id)
    edges = repository.prerequisite_status(student_id, topic_id)
    with repository._connect() as connection:
        successors = [dict(row) for row in connection.execute("""SELECT t.id,t.title,t.course,p.relation_type,p.reason
            FROM topic_prerequisites p JOIN curriculum_topics t ON t.id=p.topic_id
            WHERE p.prerequisite_topic_id=? ORDER BY t.course,t.order_index""", (topic_id,))]
    return {"topic_id":topic_id,"owner_course":topic["course"],"rule_version":"content-v1","can_browse":True,"can_study":True,
        "can_checkpoint":_can_checkpoint(request,student_id,topic),
        **{kind:[edge for edge in edges if edge["relation_type"]==kind] for kind in ("required","recommended","related")},
        "unmet":[edge for edge in edges if edge["relation_type"]=="required" and edge["scope"]=="topic" and not edge["satisfied"]],
        "successors":successors}


class SupplementQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=8000)


@router.post("/topics/{topic_id}/prerequisites/{prerequisite_id}/ask", response_model=ChatResponse)
async def ask_prerequisite(topic_id: str, prerequisite_id: str, payload: SupplementQuestion, request: Request):
    repository = request.app.state.learning_repository
    repository.require_topic(topic_id)
    declared = repository.list_prerequisites(topic_id)
    if not any(edge["id"] == prerequisite_id for edge in declared):
        raise HTTPException(403, detail={"code":"RETRIEVAL_SCOPE_FORBIDDEN","message":"该知识点未声明这一补学范围，请从前置知识卡片进入。"})
    topic = repository.require_topic(prerequisite_id)
    course = Course(topic["course"])
    agent = agent_from_request(request)
    return ChatResponse.model_validate(await agent.answer(
        course=course, question=payload.message, history=[], topic_id=prerequisite_id,
        system_prompt=f"只回答前置知识点：{topic['title']}。"))
