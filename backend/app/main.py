from __future__ import annotations

import logging
import inspect
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.chat import router as chat_router
from app.api.admins import router as admins_router
from app.api.curriculum import router as curriculum_router
from app.api.health import router as health_router
from app.api.learning import router as learning_router
from app.api.students import router as students_router
from app.api.course_content import router as course_content_router
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging
from app.curriculum.seed import seed_curriculum
from app.services.dify import DifyClient
from app.services.learning_repository import LearningRepository
from app.services.admin_repository import AdminRepository


logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    llm_client: Any = None,
    learning_repository: LearningRepository | None = None,
    admin_repository: AdminRepository | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(
        app_settings.app_log_level,
        (
            app_settings.dify_api_key.get_secret_value(),
            app_settings.admin_authcode.get_secret_value(),
        ),
    )
    app_learning_repository = learning_repository or LearningRepository(
        app_settings.database_url
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        # The bundled curriculum is configuration data.  Its upsert is
        # intentionally idempotent; database schema must be initialized first
        # with operations/database/initialize.py.
        seed_curriculum(app_learning_repository)
        try:
            yield
        finally:
            for client_name in ("llm_client",):
                client = getattr(application.state, client_name, None)
                close = getattr(client, "close", None)
                if close is None:
                    continue
                try:
                    result = close()
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    logger.exception("关闭 %s 失败", client_name)

    app = FastAPI(
        title="Course Coach API",
        version=__version__,
        description="Dify 学习助手、课程目录与学生账户后端",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.learning_repository = app_learning_repository
    app.state.admin_repository = admin_repository or AdminRepository(app_settings.database_url)
    app.state.llm_client = llm_client if llm_client is not None else DifyClient(app_settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("应用服务异常 [%s]: %s", exc.code, exc.internal_message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.info("请求参数校验失败: %s (%d errors)", request.url.path, len(exc.errors()))
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_error", "message": "请求参数无效"}},
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": str(exc.detail)}},
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理的服务器异常: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "服务器暂时无法处理请求"}},
        )

    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(students_router)
    app.include_router(admins_router)
    app.include_router(curriculum_router)
    app.include_router(learning_router)
    app.include_router(course_content_router)
    return app


app = create_app()
