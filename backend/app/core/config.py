from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All environment-backed application configuration in one place."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env.local",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_log_level: str = "INFO"

    frontend_origin: str = "http://localhost:3000"

    dify_api_base_url: str = "https://api.dify.ai/v1"
    dify_api_key: SecretStr = SecretStr("")
    dify_timeout_seconds: float = Field(default=120, gt=0, le=600)
    dify_inputs: dict[str, Any] = Field(default_factory=dict)

    database_url: str = "postgresql://postgres:postgres@localhost:5432/ml_coach"

    max_history_messages: int = Field(default=12, ge=0, le=100)
    max_message_length: int = Field(default=8000, ge=1, le=100_000)

    practice_default_count: int = Field(default=3, ge=1, le=8)
    checkpoint_default_count: int = Field(default=5, ge=1, le=8)
    practice_max_count: int = Field(default=8, ge=1, le=8)

    mastery_gate_threshold: float = Field(default=0.80, ge=0, le=1)
    prerequisite_mastery_threshold: float = Field(default=0.80, ge=0, le=1)
    mastery_min_valid_attempts: int = Field(default=3, ge=1)
    mastery_checkpoint_score: float = Field(default=80, ge=0, le=100)
    mastery_min_dimension_coverage: int = Field(default=3, ge=1)
    mastery_evidence_confidence_target: float = Field(default=6, gt=0)

    evaluator_min_confidence: float = Field(default=0.60, ge=0, le=1)
    evaluation_max_repair_attempts: int = Field(default=1, ge=0, le=1)

    practice_generation_temperature: float = Field(default=0.30, ge=0, le=2)
    evaluation_temperature: float = Field(default=0.00, ge=0, le=2)
    remediation_temperature: float = Field(default=0.20, ge=0, le=2)

    recent_question_dedup_count: int = Field(default=10, ge=1, le=100)
    question_generation_max_retries: int = Field(default=1, ge=0, le=1)

    @model_validator(mode="after")
    def validate_and_resolve(self) -> "Settings":
        if self.practice_default_count > self.practice_max_count:
            raise ValueError("PRACTICE_DEFAULT_COUNT 不能大于 PRACTICE_MAX_COUNT")
        if self.checkpoint_default_count > self.practice_max_count:
            raise ValueError("CHECKPOINT_DEFAULT_COUNT 不能大于 PRACTICE_MAX_COUNT")
        origins = self.cors_origins
        if self.app_env == "production" and "*" in origins:
            raise ValueError("生产环境不允许 FRONTEND_ORIGIN 使用通配符")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.frontend_origin.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
