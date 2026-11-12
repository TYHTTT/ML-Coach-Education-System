"""Stable canonical curriculum navigation."""
from __future__ import annotations

from fastapi import APIRouter, Header, Request

from app.core.types import Course
from app.api.dependencies import student_id_from_authorization

router = APIRouter(prefix="/api/v1", tags=["course-content"])


@router.get("/courses/{course}/outline")
def outline(course: Course, request: Request, authorization: str | None = Header(default=None, alias="Authorization")):
    repository = request.app.state.learning_repository
    course_record = repository.require_course(course)
    student_id = student_id_from_authorization(authorization, repository)
    with repository._connect() as connection:
        placements = [dict(row) for row in connection.execute("""SELECT p.*,t.title,t.description,t.course AS owner_course,owner.title AS owner_title
            FROM topic_placements p JOIN curriculum_topics t ON t.id=p.topic_id JOIN courses owner ON owner.id=t.course AND owner.active=1 AND owner.deleted_at IS NULL
            WHERE p.course_id=? AND t.active=1 ORDER BY CASE WHEN p.parent_group_id ~ '^stage-[0-9]+$' THEN split_part(p.parent_group_id,'-',2)::integer ELSE t.stage END,p.order_index,t.id""", (course.value,))]
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
    groups: dict[str, dict] = {}
    recommended = None
    for placement in placements:
        topic_id = placement["topic_id"]
        topic = topics[topic_id]
        state = states.get(topic_id)
        group_id = placement["parent_group_id"]
        group = groups.setdefault(group_id, {"id":group_id,"title":placement["group_title"],"parent_group_id":None,"order_index":len(groups),"topics":[]})
        status = state["status"] if state else "not_started"
        group["topics"].append({"id":topic_id,"topic_id":topic_id,"owner_course":placement["owner_course"],
            "title":topic["title"],"description":topic["description"],"learning_objectives":topic["learning_objectives"],
            "order_index":placement["order_index"],"is_reference":bool(placement["is_reference"]),"status":status,
            "mastery":float(state["mastery"]) if state and state["evidence_count"] else None})
        if recommended is None and status!="mastered":
            recommended = topic_id
    return {"course":course.value,"title":course_record["title"],"groups":list(groups.values()),"recommended_topic_id":recommended}
