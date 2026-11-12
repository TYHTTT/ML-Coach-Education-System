from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.schemas.student import LoginRequest, RegisterStudentRequest


class RegisterAdminRequest(RegisterStudentRequest):
    model_config = ConfigDict(extra="forbid")
    authcode: SecretStr = Field(min_length=1, max_length=512)

    @field_validator("display_name")
    @classmethod
    def nonempty_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("姓名不能为空")
        return value.strip()


class LoginAdminRequest(LoginRequest):
    model_config = ConfigDict(extra="forbid")


class CurrentAdminResponse(BaseModel):
    admin_id: str
    username: str
    display_name: str
    role: Literal["admin"] = "admin"
    created_at: datetime
    last_active_at: datetime


class AuthenticatedAdminResponse(CurrentAdminResponse):
    access_token: str
