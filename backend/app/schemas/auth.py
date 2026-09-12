from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.types import ensure_utc


class LoginRequest(BaseModel):
    """接收现有前端提交的用户名和原始密码。"""

    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1)


class RoleSummary(BaseModel):
    """输出用户关联角色的精简标识。"""

    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str


class GroupSummary(RoleSummary):
    """输出用户关联用户组的精简标识。"""


class UserResponse(BaseModel):
    """输出前端登录态需要的账号、角色和权限信息。"""

    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str
    first_name: str
    last_name: str
    is_active: bool
    is_staff: bool
    is_superuser: bool
    date_joined: datetime
    last_login: datetime | None
    roles: list[RoleSummary]
    user_groups: list[GroupSummary]
    effective_permissions: list[str]
    display_name: str
    is_demo_account: Literal[False] = False

    @field_validator("date_joined", "last_login")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        """保证账号时间字段以 UTC 时区输出，兼容无时区数据库值。"""
        return None if value is None else ensure_utc(value)


class LoginResponse(BaseModel):
    """返回只出现一次的原始令牌和当前用户资料。"""

    token: str
    user: UserResponse


class SyncResponse(BaseModel):
    """返回内置权限和角色同步结果。"""

    success: bool = True
    message: str
