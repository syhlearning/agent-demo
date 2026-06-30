from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[0-9A-Za-z._-]+$")
    password: str = Field(min_length=8, max_length=128)
    email: EmailStr | None = Field(default=None, max_length=320)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_empty_email(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return value

    @field_validator("email")
    @classmethod
    def normalize_email_case(cls, value: EmailStr | None) -> str | None:
        if value is None:
            return None
        return str(value).lower()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: str | None = None
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    refresh_expires_in: int
    user: UserRead


class MessageResponse(BaseModel):
    ok: bool
    message: str
