"""提供角色、用户组及权限字典的关系预加载和响应构造。"""

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import PermissionDefinition, Role, UserGroup
from app.schemas.rbac import GroupResponse, PermissionResponse, RoleResponse
from app.core.exceptions import BusinessError
from app.models import User
from app.selectors.accounts import user_load_options
from app.models.rbac import group_roles, group_users, user_roles


def role_options() -> tuple[object, ...]:
    """预加载角色输出和写入所需的权限及直接成员。"""
    return selectinload(Role.permissions), selectinload(Role.users)


def group_options() -> tuple[object, ...]:
    """预加载用户组输出及权限校验需要的组角色权限和成员。"""
    return selectinload(UserGroup.roles).selectinload(Role.permissions), selectinload(UserGroup.users)


async def get_role(session: AsyncSession, role_id: int) -> Role:
    """返回指定角色及关系，不存在时返回 404。"""
    role = await session.scalar(select(Role).where(Role.id == role_id).options(*role_options()).execution_options(populate_existing=True))
    if role is None:
        raise HTTPException(404, detail="角色不存在。")
    return role


async def get_group(session: AsyncSession, group_id: int) -> UserGroup:
    """返回指定用户组及关系，不存在时返回 404。"""
    group = await session.scalar(select(UserGroup).where(UserGroup.id == group_id).options(*group_options()).execution_options(populate_existing=True))
    if group is None:
        raise HTTPException(404, detail="用户组不存在。")
    return group


async def list_roles(session: AsyncSession, search: str = "") -> list[Role]:
    """查询角色数组，并批量预加载嵌套权限和成员。"""
    statement = select(Role).order_by(Role.id).options(*role_options())
    if search:
        statement = statement.where(or_(Role.code.icontains(search), Role.name.icontains(search), Role.description.icontains(search)))
    return list((await session.scalars(statement)).all())


async def list_groups(session: AsyncSession, search: str = "") -> list[UserGroup]:
    """查询用户组数组，并批量预加载角色和成员关系。"""
    statement = select(UserGroup).order_by(UserGroup.id).options(*group_options())
    if search:
        statement = statement.where(or_(UserGroup.code.icontains(search), UserGroup.name.icontains(search), UserGroup.description.icontains(search)))
    return list((await session.scalars(statement)).all())


async def list_permissions(session: AsyncSession, search: str = "") -> list[PermissionDefinition]:
    """只读查询权限字典，按配置顺序和 ID 稳定输出。"""
    statement = select(PermissionDefinition).order_by(PermissionDefinition.sort_order, PermissionDefinition.id)
    if search:
        statement = statement.where(or_(*(column.icontains(search) for column in (PermissionDefinition.code, PermissionDefinition.name, PermissionDefinition.category, PermissionDefinition.description))))
    return list((await session.scalars(statement)).all())


def serialize_role(role: Role) -> RoleResponse:
    """将已加载角色关系转换为前端可直接编辑的响应。"""
    return RoleResponse(id=role.id, code=role.code, name=role.name, description=role.description, is_builtin=role.is_builtin, permissions=sorted(role.permissions, key=lambda item: item.id), permissions_count=len(role.permissions), users_count=len(role.users), created_at=role.created_at, updated_at=role.updated_at)


def serialize_group(group: UserGroup) -> GroupResponse:
    """将已加载组成员和角色转换为精简、稳定排序的响应。"""
    return GroupResponse(id=group.id, code=group.code, name=group.name, description=group.description, is_builtin=group.is_builtin, roles=sorted(group.roles, key=lambda item: item.id), users=sorted(group.users, key=lambda item: item.id), roles_count=len(group.roles), users_count=len(group.users), created_at=group.created_at, updated_at=group.updated_at)


async def resolve_ids(session: AsyncSession, model: type, ids: list[int]) -> list:
    """一次查询验证所有关联 ID 并去重，缺失任意对象就拒绝整次修改。"""
    unique_ids = sorted(set(ids))
    statement = select(model).where(model.id.in_(unique_ids)).order_by(model.id)
    if model is Role:
        statement = statement.options(*role_options())
    elif model is UserGroup:
        statement = statement.options(*group_options())
    elif model is User:
        statement = statement.options(*user_load_options())
    values = list((await session.scalars(statement)).all())
    if len(values) != len(unique_ids):
        raise BusinessError("关联的账号、角色、用户组或权限 ID 不存在。")
    return values


async def role_affected_users(session: AsyncSession, role_id: int) -> list[User]:
    """查询直接绑定及通过组继承角色的所有账号，用于变更前权限边界检查。"""
    direct = select(user_roles.c.user_id).where(user_roles.c.role_id == role_id)
    grouped = select(group_users.c.user_id).join(group_roles, group_roles.c.group_id == group_users.c.group_id).where(group_roles.c.role_id == role_id)
    statement = select(User).where(User.id.in_(direct.union(grouped))).order_by(User.id).options(*user_load_options())
    return list((await session.scalars(statement)).all())
