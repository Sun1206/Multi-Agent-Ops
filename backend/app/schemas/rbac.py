"""定义用户管理页面的权限、角色、用户组和分页输出。"""

from datetime import datetime

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator

from app.schemas.auth import RoleSummary, UserResponse


class PermissionResponse(BaseModel):
    """输出稳定的权限字典字段，不包含内部关系。"""

    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    category: str
    description: str
    sort_order: int
    is_builtin: bool


class RoleResponse(BaseModel):
    """输出角色、权限集合及关联数量，供角色编辑表单使用。"""

    id: int
    code: str
    name: str
    description: str
    is_builtin: bool
    permissions: list[PermissionResponse]
    permissions_count: int
    users_count: int
    created_at: datetime
    updated_at: datetime


class UserLiteResponse(BaseModel):
    """输出用户组成员选择和展示所需的精简账号信息。"""

    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str


class GroupResponse(BaseModel):
    """输出用户组的角色和成员绑定关系及数量。"""

    id: int
    code: str
    name: str
    description: str
    is_builtin: bool
    roles: list[RoleSummary]
    users: list[UserLiteResponse]
    roles_count: int
    users_count: int
    created_at: datetime
    updated_at: datetime


class UserPageResponse(BaseModel):
    """保留前端使用的 count/results 和前后页链接契约。"""

    count: int
    next: str | None
    previous: str | None
    results: list[UserResponse]


Password = Annotated[str, Field(min_length=8, max_length=128)]
Identity = Annotated[str, Field(min_length=1, max_length=64)]


class MutationInput(BaseModel):
    """禁止客户端注入只读字段，并统一修剪非密码的身份字段。"""

    model_config = ConfigDict(extra="forbid")

    @field_validator("username", "code", "name", mode="before", check_fields=False)
    @classmethod
    def trim_identity(cls, value: object) -> object:
        """修剪标识首尾空白，后续长度验证拒绝空标识。"""
        return value.strip() if isinstance(value, str) else value


class UserPatch(MutationInput):
    """接收部分用户修改；服务只使用显式提交的字段，缺省值不写入。"""

    username: Annotated[str, Field(min_length=1, max_length=150)] = ""
    email: Annotated[str, Field(max_length=254)] = ""
    first_name: Annotated[str, Field(max_length=150)] = ""
    last_name: Annotated[str, Field(max_length=150)] = ""
    password: Password = ""
    is_active: bool = True
    is_staff: bool = False
    is_superuser: bool = False
    role_ids: list[PositiveInt] = []
    group_ids: list[PositiveInt] = []


class UserCreate(UserPatch):
    """创建账号必须提供用户名和至少八位原始密码。"""

    username: Annotated[str, Field(min_length=1, max_length=150)]
    password: Password


class RolePatch(MutationInput):
    """接收角色的部分字段修改及权限集合替换。"""

    code: Identity = ""
    name: Identity = ""
    description: Annotated[str, Field(max_length=255)] = ""
    permission_ids: list[PositiveInt] = []


class RoleCreate(RolePatch):
    """创建角色时必须提供稳定编码及展示名称。"""

    code: Identity
    name: Identity


class GroupPatch(MutationInput):
    """接收用户组部分修改及角色/成员集合替换。"""

    code: Identity = ""
    name: Identity = ""
    description: Annotated[str, Field(max_length=255)] = ""
    role_ids: list[PositiveInt] = []
    user_ids: list[PositiveInt] = []


class GroupCreate(GroupPatch):
    """创建用户组时必须提供编码及展示名称。"""

    code: Identity
    name: Identity


class PasswordReset(MutationInput):
    """接收密码重置请求，不允许其他字段混入。"""

    password: Password
