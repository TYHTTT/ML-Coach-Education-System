from __future__ import annotations


class AppError(Exception):
    status_code = 500
    code = "internal_error"
    public_message = "服务器暂时无法处理请求"

    def __init__(self, message: str | None = None, *, internal_message: str | None = None) -> None:
        super().__init__(internal_message or message or self.public_message)
        self.message = message or self.public_message
        self.internal_message = internal_message or self.message


class ConfigurationError(AppError):
    status_code = 503
    code = "service_not_configured"
    public_message = "服务尚未完成配置"


class LLMServiceError(AppError):
    status_code = 502
    code = "LLM_SERVICE_UNAVAILABLE"
    public_message = "大模型服务暂时不可用，请稍后重试"


class StudentNotFoundError(AppError):
    status_code = 404
    code = "STUDENT_NOT_FOUND"
    public_message = "未找到该匿名学生，请重新进入学习页面"


class TopicNotFoundError(AppError):
    status_code = 404
    code = "TOPIC_NOT_FOUND"
    public_message = "未找到该课程知识点"


class CourseTopicMismatchError(AppError):
    status_code = 422
    code = "COURSE_TOPIC_MISMATCH"
    public_message = "知识点不属于当前课程"


class TopicLockedError(AppError):
    status_code = 409
    code = "TOPIC_LOCKED"
    public_message = "该知识点的前置要求尚未完成"


class KnowledgeInsufficientError(AppError):
    status_code = 422
    code = "KNOWLEDGE_INSUFFICIENT"
    public_message = "Dify 未返回足够的可引用课程资料，请检查 Dify 知识检索与引用配置。"


class PracticeSetNotFoundError(AppError):
    status_code = 404
    code = "PRACTICE_SET_NOT_FOUND"
    public_message = "未找到该练习集合"


class PracticeSetAlreadySubmittedError(AppError):
    status_code = 409
    code = "PRACTICE_SET_ALREADY_SUBMITTED"
    public_message = "该练习集合已经提交"


class InvalidQuestionAnswerError(AppError):
    status_code = 422
    code = "INVALID_QUESTION_ANSWER"
    public_message = "提交的题目答案无效"


class EvaluationUncertainError(AppError):
    status_code = 422
    code = "EVALUATION_UNCERTAIN"
    public_message = "当前评价证据不足或结果不可靠，请重新提交或生成练习"


class StructuredOutputInvalidError(AppError):
    status_code = 502
    code = "LLM_STRUCTURED_OUTPUT_INVALID"
    public_message = "模型返回的结构化结果无效，请稍后重试"


class DuplicateSubmissionError(AppError):
    status_code = 409
    code = "DUPLICATE_SUBMISSION"
    public_message = "该提交正在处理或已经处理"
