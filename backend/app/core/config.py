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

    admin_authcode: SecretStr = SecretStr("")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/ml_coach"

    max_history_messages: int = Field(default=12, ge=0, le=100)
    max_message_length: int = Field(default=8000, ge=1, le=100_000)

    mastery_gate_threshold: float = Field(default=0.80, ge=0, le=1)
    prerequisite_mastery_threshold: float = Field(default=0.80, ge=0, le=1)
    mastery_min_valid_attempts: int = Field(default=3, ge=1)
    mastery_checkpoint_score: float = Field(default=80, ge=0, le=100)
    mastery_min_dimension_coverage: int = Field(default=3, ge=1)

    @model_validator(mode="after")
    def validate_and_resolve(self) -> "Settings":
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
