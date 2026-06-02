"""Authentication schemas."""
from typing import Optional
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    token: str
    user: dict


class UserResponse(BaseModel):
    user: dict


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)
    role: str = "user"
    email: str = ""


class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None


class RegistrationRequest(BaseModel):
    username: str
    password: str
    email: str = ""


class ResetPasswordRequest(BaseModel):
    password: str


class FieldVisibilityUpdate(BaseModel):
    """Dict of field_name -> visible (bool). Accepts extra fields."""
    model_config = {"extra": "allow"}


class AIPromptUpdate(BaseModel):
    prompt: str = ""
