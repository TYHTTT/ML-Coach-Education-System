from fastapi import APIRouter, Depends, Query, Request, Path
from app.api.admins import require_admin
from app.core.types import Course
from app.schemas.topic_management import TopicId, TopicWrite, TopicOrder, StageRename, StageOrder
from app.services.topic_management import TopicManagement

router = APIRouter(tags=["topic-management"], dependencies=[Depends(require_admin)])
PREFIX = "/api/v1/admin/courses/{course_id}/topics"


def service(request: Request): return TopicManagement(request.app.state.settings.database_url)


@router.get("/api/v1/admin/related-topics")
def related_topic_candidates(q: str = Query(default="", max_length=100), course_id: Course | None = None,
                             exclude_topic_id: TopicId | None = None, page: int = Query(default=1, ge=1),
                             page_size: int = Query(default=30, ge=1, le=100), manager=Depends(service)):
    return manager.related_candidates(q, course_id, exclude_topic_id, page, page_size)




@router.get(PREFIX)
def outline(course_id: Course, manager=Depends(service)): return manager.outline(course_id)


@router.post(PREFIX, status_code=201)
def create(course_id: Course, payload: TopicWrite, manager=Depends(service)):
    return manager.save(course_id, payload.model_dump())




@router.put(PREFIX + "/order")
def reorder(course_id: Course, payload: TopicOrder, manager=Depends(service)):
    return manager.reorder(course_id, payload.group_id, payload.topic_ids)


@router.patch(PREFIX + "/groups/{stage}")
def rename_group(course_id: Course, payload: StageRename, stage: int = Path(ge=1, le=999), manager=Depends(service)):
    return manager.rename_stage(course_id, stage, payload.title)


@router.post(PREFIX + "/groups/order")
def reorder_groups(course_id: Course, payload: StageOrder, manager=Depends(service)):
    return manager.reorder_stages(course_id, payload.group_ids)


@router.put(PREFIX + "/{topic_id}")
def update(course_id: Course, topic_id: TopicId, payload: TopicWrite, manager=Depends(service)):
    return manager.save(course_id, payload.model_dump(), topic_id)


@router.delete(PREFIX + "/{topic_id}")
def remove(course_id: Course, topic_id: TopicId, manager=Depends(service)):
    return manager.remove(course_id, topic_id)


@router.post(PREFIX + "/{topic_id}/restore")
def restore(course_id: Course, topic_id: TopicId, manager=Depends(service)):
    return manager.remove(course_id, topic_id, restore=True)
