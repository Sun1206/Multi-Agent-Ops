# 处理角色资料和权限集合写入，不自行提交事务。

from sqlalchemy import delete
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PermissionDefinition, Role, User
from app.selectors.rbac import get_role, resolve_ids, role_affected_users
from app.services.rbac_policy import check_users_boundary, protect_builtin, require_permission_subset, role_codes


async def create_role(session: AsyncSession, actor: User, data: dict) -> Role:
    values = dict(data)
    permissions = await resolve_ids(session, PermissionDefinition, values.pop("permission_ids", []))
    await require_permission_subset(session, actor, {permission.code for permission in permissions})
    role = Role(**values, permissions=permissions, users=[])
    session.add(role)
    await session.flush()
    return await get_role(session, role.id)


async def update_role(session: AsyncSession, actor: User, role_id: int, data: dict) -> Role:
    role = await get_role(session, role_id)
    protect_builtin(role, data)
    if role.is_builtin and not actor.is_superuser:
        raise HTTPException(403, detail="只有超级管理员可以编辑内置角色。")
    await require_permission_subset(session, actor, role_codes([role]))
    await check_users_boundary(session, actor, await role_affected_users(session, role.id))
    values = dict(data)
    permissions = await resolve_ids(session, PermissionDefinition, values.pop("permission_ids")) if "permission_ids" in values else None
    if permissions is not None:
        await require_permission_subset(session, actor, {permission.code for permission in permissions})
    for name, value in values.items():
        setattr(role, name, value)
    if permissions is not None:
        role.permissions = permissions
    await session.flush()
    return await get_role(session, role.id)


async def delete_role(session: AsyncSession, actor: User, role_id: int) -> Role:
    role = await get_role(session, role_id)
    protect_builtin(role, {}, deleting=True)
    await require_permission_subset(session, actor, role_codes([role]))
    await check_users_boundary(session, actor, await role_affected_users(session, role.id))
    await session.execute(delete(Role).where(Role.id == role_id))
    await session.flush()
    return role
