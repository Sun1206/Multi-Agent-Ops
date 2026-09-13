from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.types import ensure_utc


class LoginRequest(BaseModel):
    model_config = {'json_schema_extra': {'description': "接收现有前端提交的用户名和原始密码。"}}

    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1)


class RoleSummary(BaseModel):

    model_config = ConfigDict(from_attributes=True, json_schema_extra={'description': '输出用户关联角色的精简标识。'})
    id: int
    code: str
    name: str


class GroupSummary(RoleSummary):
    model_config = {'json_schema_extra': {'description': "输出用户关联用户组的精简标识。"}}


class UserResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True, json_schema_extra={'description': '输出前端登录态需要的账号、角色和权限信息。'})
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
        return None if value is None else ensure_utc(value)


class LoginResponse(BaseModel):
    model_config = {'json_schema_extra': {'description': "返回只出现一次的原始令牌和当前用户资料。"}}

    token: str
    user: UserResponse


class SyncResponse(BaseModel):
    model_config = {'json_schema_extra': {'description': "返回内置权限和角色同步结果。"}}

    success: bool = True
    message: str
