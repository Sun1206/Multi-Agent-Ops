# 处理用户组资料、组角色及成员绑定，不自行提交事务。

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from rbac.models import Role, User, UserGroup
from rbac.selectors.authorization import get_group, resolve_ids
from rbac.services.policy import check_users_boundary, protect_builtin, require_permission_subset, role_codes


async def create_group(session: AsyncSession, actor: User, data: dict) -> UserGroup:
    values = dict(data)
    roles = await resolve_ids(session, Role, values.pop("role_ids", []))
    users = await resolve_ids(session, User, values.pop("user_ids", []))
    await require_permission_subset(session, actor, role_codes(roles))
    await check_users_boundary(session, actor, users)
    group = UserGroup(**values, roles=roles, users=users)
    session.add(group)
    await session.flush()
    return await get_group(session, group.id)


async def update_group(session: AsyncSession, actor: User, group_id: int, data: dict) -> UserGroup:
    group = await get_group(session, group_id)
    protect_builtin(group, data)
    await require_permission_subset(session, actor, role_codes(group.roles))
    await check_users_boundary(session, actor, group.users)
    values = dict(data)
    roles = await resolve_ids(session, Role, values.pop("role_ids")) if "role_ids" in values else None
    users = await resolve_ids(session, User, values.pop("user_ids")) if "user_ids" in values else None
    if roles is not None:
        await require_permission_subset(session, actor, role_codes(roles))
    if users is not None:
        await check_users_boundary(session, actor, users)
    for name, value in values.items():
        setattr(group, name, value)
    if roles is not None:
        group.roles = roles
    if users is not None:
        group.users = users
    await session.flush()
    return await get_group(session, group.id)


async def delete_group(session: AsyncSession, actor: User, group_id: int) -> UserGroup:
    group = await get_group(session, group_id)
    protect_builtin(group, {}, deleting=True)
    await require_permission_subset(session, actor, role_codes(group.roles))
    await check_users_boundary(session, actor, group.users)
    await session.execute(delete(UserGroup).where(UserGroup.id == group_id))
    await session.flush()
    return group
