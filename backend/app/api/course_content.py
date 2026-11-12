"""Stable canonical curriculum navigation."""
from __future__ import annotations

from fastapi import APIRouter, Header, Request

from app.core.types import Course
from app.api.dependencies import student_id_from_authorization

router = APIRouter(prefix="/api/v1", tags=["course-content"])


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
