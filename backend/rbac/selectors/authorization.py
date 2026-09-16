# 提供角色、用户组及权限字典的关系预加载和响应构造。

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rbac.models import PermissionDefinition, Role, UserGroup
from rbac.schemas.authorization import GroupResponse, PermissionResponse, RoleResponse
from aidevops.exceptions import BusinessError
from rbac.models import User
from rbac.selectors.accounts import user_load_options
from rbac.models.authorization import group_roles, group_users, user_roles


def role_options() -> tuple[object, ...]:
    return selectinload(Role.permissions), selectinload(Role.users)


def group_options() -> tuple[object, ...]:
    return selectinload(UserGroup.roles).selectinload(Role.permissions), selectinload(UserGroup.users)


async def get_role(session: AsyncSession, role_id: int) -> Role:
    role = await session.scalar(select(Role).where(Role.id == role_id).options(*role_options()).execution_options(populate_existing=True))
    if role is None:
        raise HTTPException(404, detail="角色不存在。")
    return role


async def get_group(session: AsyncSession, group_id: int) -> UserGroup:
    group = await session.scalar(select(UserGroup).where(UserGroup.id == group_id).options(*group_options()).execution_options(populate_existing=True))
    if group is None:
        raise HTTPException(404, detail="用户组不存在。")
    return group


async def list_roles(session: AsyncSession, search: str = "") -> list[Role]:
    statement = select(Role).order_by(Role.id).options(*role_options())
    if search:
        statement = statement.where(or_(Role.code.icontains(search), Role.name.icontains(search), Role.description.icontains(search)))
    return list((await session.scalars(statement)).all())


async def list_groups(session: AsyncSession, search: str = "") -> list[UserGroup]:
    statement = select(UserGroup).order_by(UserGroup.id).options(*group_options())
    if search:
        statement = statement.where(or_(UserGroup.code.icontains(search), UserGroup.name.icontains(search), UserGroup.description.icontains(search)))
    return list((await session.scalars(statement)).all())


async def list_permissions(session: AsyncSession, search: str = "") -> list[PermissionDefinition]:
    statement = select(PermissionDefinition).order_by(PermissionDefinition.sort_order, PermissionDefinition.id)
    if search:
        statement = statement.where(or_(*(column.icontains(search) for column in (PermissionDefinition.code, PermissionDefinition.name, PermissionDefinition.category, PermissionDefinition.description))))
    return list((await session.scalars(statement)).all())


def serialize_role(role: Role) -> RoleResponse:
    return RoleResponse(id=role.id, code=role.code, name=role.name, description=role.description, is_builtin=role.is_builtin, permissions=sorted(role.permissions, key=lambda item: item.id), permissions_count=len(role.permissions), users_count=len(role.users), created_at=role.created_at, updated_at=role.updated_at)


def serialize_group(group: UserGroup) -> GroupResponse:
    return GroupResponse(id=group.id, code=group.code, name=group.name, description=group.description, is_builtin=group.is_builtin, roles=sorted(group.roles, key=lambda item: item.id), users=sorted(group.users, key=lambda item: item.id), roles_count=len(group.roles), users_count=len(group.users), created_at=group.created_at, updated_at=group.updated_at)


async def resolve_ids(session: AsyncSession, model: type, ids: list[int]) -> list:
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
    direct = select(user_roles.c.user_id).where(user_roles.c.role_id == role_id)
    grouped = select(group_users.c.user_id).join(group_roles, group_roles.c.group_id == group_users.c.group_id).where(group_roles.c.role_id == role_id)
    statement = select(User).where(User.id.in_(direct.union(grouped))).order_by(User.id).options(*user_load_options())
    return list((await session.scalars(statement)).all())
