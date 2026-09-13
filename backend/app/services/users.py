# 处理用户写入和令牌撤销；事务提交由调用方控制。

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import AuthToken, Role, User, UserGroup
from app.selectors.rbac import resolve_ids
from app.selectors.users import get_user
from app.services.rbac_policy import check_user_relations, check_users_boundary, lock_superusers, protect_identity, protect_last_admin
from app.core.exceptions import BusinessError


async def create_user(session: AsyncSession, actor: User, data: dict) -> User:
    values = dict(data)
    await lock_superusers(session)
    protect_identity(actor, None, values)
    roles = await resolve_ids(session, Role, values.pop("role_ids", []))
    groups = await resolve_ids(session, UserGroup, values.pop("group_ids", []))
    await check_user_relations(session, actor, roles=roles, groups=groups)
    password = values.pop("password")
    user = User(**values, password_hash=hash_password(password), roles=roles, groups=groups)
    session.add(user)
    await session.flush()
    return await get_user(session, user.id)


async def update_user(session: AsyncSession, actor: User, user_id: int, data: dict) -> User:
    admins = await lock_superusers(session)
    user = await get_user(session, user_id, for_update=True)
    protect_identity(actor, user, data)
    protect_last_admin(admins, user, data)
    await check_users_boundary(session, actor, [user])
    values = dict(data)
    roles = await resolve_ids(session, Role, values.pop("role_ids")) if "role_ids" in values else None
    groups = await resolve_ids(session, UserGroup, values.pop("group_ids")) if "group_ids" in values else None
    current_roles = await resolve_ids(session, Role, [role.id for role in user.roles]) if roles is None else roles
    current_groups = await resolve_ids(session, UserGroup, [group.id for group in user.groups]) if groups is None else groups
    await check_user_relations(session, actor, roles=current_roles, groups=current_groups)
    password = values.pop("password", None)
    if password is not None:
        user.password_hash = hash_password(password)
    for name, value in values.items():
        setattr(user, name, value)
    if roles is not None:
        user.roles = roles
    if groups is not None:
        user.groups = groups
    if password is not None or values.get("is_active") is False:
        await revoke_user_tokens(session, user.id)
    await session.flush()
    return await get_user(session, user.id, for_update=True)


async def revoke_user_tokens(session: AsyncSession, user_id: int) -> None:
    await session.execute(delete(AuthToken).where(AuthToken.user_id == user_id))


async def reset_password(session: AsyncSession, actor: User, user_id: int, password: str) -> User:
    await lock_superusers(session)
    user = await get_user(session, user_id, for_update=True)
    protect_identity(actor, user, {})
    await check_users_boundary(session, actor, [user])
    user.password_hash = hash_password(password)
    await revoke_user_tokens(session, user_id)
    await session.flush()
    return user


async def delete_user(session: AsyncSession, actor: User, user_id: int) -> User:
    admins = await lock_superusers(session)
    user = await get_user(session, user_id, for_update=True)
    protect_identity(actor, user, {})
    if actor.id == user_id:
        raise BusinessError("不能删除当前登录账号。")
    protect_last_admin(admins, user, {}, deleting=True)
    await check_users_boundary(session, actor, [user])
    await session.execute(delete(User).where(User.id == user_id))
    await session.flush()
    return user
