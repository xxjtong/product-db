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
    # 三态：None=跟随全局成本可见性开关
    can_view_cost: Optional[bool] = None


class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
    # 三态：None=跟随全局；显式传 null 表示「改回跟随全局」（见 admin_routes.update_user）
    can_view_cost: Optional[bool] = None


class UpdateProfileRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    current_password: Optional[str] = None


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
