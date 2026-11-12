from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RegisterStudentRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128, repr=False)
    display_name: str = Field(min_length=1, max_length=64)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=128, repr=False)


class AuthenticatedStudentResponse(BaseModel):
    student_id: str
    username: str
    display_name: str
    access_token: str
    created_at: datetime


class CurrentStudentResponse(BaseModel):
    student_id: str
    username: str
    display_name: str
    created_at: datetime
