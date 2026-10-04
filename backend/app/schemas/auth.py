from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import Role

MIN_PASSWORD_LENGTH = 8
# bcrypt ignores bytes past 72, so the limit is enforced at the boundary rather
# than silently truncating two users' distinct passwords into the same hash.
MAX_PASSWORD_LENGTH = 72


def _check_password_bounds(v: str) -> str:
    if len(v.encode("utf-8")) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} bytes")
    return v


class UserRegister(BaseModel):
    model_config = {"extra": "forbid"}

    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        v = _check_password_bounds(v)
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserLogin(BaseModel):
    model_config = {"extra": "forbid"}

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=MAX_PASSWORD_LENGTH)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: Role
    created_at: datetime

    model_config = {"from_attributes": True}
