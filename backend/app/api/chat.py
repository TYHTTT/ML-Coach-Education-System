from fastapi import APIRouter, Header, HTTPException, Request

from app.api.dependencies import agent_from_request, student_id_from_authorization
from app.core.exceptions import CourseTopicMismatchError
from app.prompts.learning import get_learning_prompt
from app.services.learning_grounding import LearningGroundingService
from app.services.conversation_tokens import issue_conversation_token, read_conversation_token
from app.schemas.chat import ChatRequest, ChatResponse


router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> ChatResponse:
    settings = request.app.state.settings
    if len(payload.message) > settings.max_message_length:
        raise HTTPException(
            status_code=422,
            detail=f"问题不能超过 {settings.max_message_length} 个字符",
        )
    if len(payload.history) > settings.max_history_messages:
        raise HTTPException(
            status_code=422,
            detail=f"history 最多包含 {settings.max_history_messages} 条消息",
        )
    history = [item.model_dump() for item in payload.history[-settings.max_history_messages :]] if settings.max_history_messages else []
    plain_query = (
        payload.learning_mode == "free_qa" and payload.topic_id is None
    ) or (
        payload.learning_mode in {"topic_teaching", "topic_clarification", "topic_practice", "topic_answer"}
        and payload.topic_id is not None
    )
    retrieval_query: str | None = None
    system_prompt: str | None = None
    repository = request.app.state.learning_repository
    student_id = student_id_from_authorization(authorization, repository)
    conversation_id = None
    scope = {
        "secret": settings.dify_api_key.get_secret_value(),
        "student_id": student_id or "", "course": payload.course.value if payload.course else "",
        "topic_id": payload.topic_id or "",
    }
    if payload.conversation_token:
        if not plain_query or not student_id:
            raise HTTPException(status_code=403, detail="该对话不属于当前学生或学习范围，请新建对话。")
        try:
            conversation_id = read_conversation_token(payload.conversation_token, **scope)
        except ValueError:
            raise HTTPException(status_code=403, detail="对话已过期或不属于当前学习范围，请重新开始学习或新建对话。") from None
    if payload.topic_id is not None:
        topic = repository.require_topic(payload.topic_id)
        if topic["course"] != payload.course.value:
            raise CourseTopicMismatchError(
                internal_message=(
                    f"topic {payload.topic_id} belongs to {topic['course']}, "
                    f"not {payload.course.value}"
                )
            )
        if not plain_query:
            retrieval_query = LearningGroundingService.build_query(
                topic=topic,
                purpose=payload.learning_mode,
                user_question=payload.message,
            )
            if payload.learning_mode in {"worked_example", "remediation"}:
                system_prompt = get_learning_prompt(payload.course, payload.learning_mode)
        if student_id is not None and payload.learning_mode != "free_qa":
            repository.create_learning_session(
                student_id=student_id,
                course=payload.course,
                topic_id=payload.topic_id,
                state=payload.learning_mode,
            )
    agent = agent_from_request(request)
    result = await agent.answer(
        course=payload.course,
        question=(retrieval_query or payload.message),
        history=history,
        system_prompt=system_prompt,
        topic_id=payload.topic_id,
        user=student_id,
        plain_query=plain_query,
        **({"conversation_id": conversation_id} if conversation_id else {}),
    )
    remote_id = result.get("conversation_id")
    if plain_query and student_id and scope["secret"] and isinstance(remote_id, str) and 1 <= len(remote_id) <= 128:
        result["conversation_token"] = issue_conversation_token(remote_id, **scope)
    return ChatResponse.model_validate(result)
