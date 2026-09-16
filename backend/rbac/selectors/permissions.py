from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rbac.models import PermissionDefinition, User
from rbac.models.authorization import group_roles, group_users, role_permissions, user_roles


async def effective_permission_codes(session: AsyncSession, user: User) -> list[str]:
    if user.is_superuser:
        statement = select(PermissionDefinition.code).order_by(PermissionDefinition.code)
        return list((await session.scalars(statement)).all())
    direct = (
        select(PermissionDefinition.code)
        .join(role_permissions, role_permissions.c.permission_id == PermissionDefinition.id)
        .join(user_roles, user_roles.c.role_id == role_permissions.c.role_id)
        .where(user_roles.c.user_id == user.id)
    )
    grouped = (
        select(PermissionDefinition.code)
        .join(role_permissions, role_permissions.c.permission_id == PermissionDefinition.id)
        .join(group_roles, group_roles.c.role_id == role_permissions.c.role_id)
        .join(group_users, group_users.c.group_id == group_roles.c.group_id)
        .where(group_users.c.user_id == user.id)
    )
    direct_codes = (await session.scalars(direct)).all()
    grouped_codes = (await session.scalars(grouped)).all()
    return sorted(set(direct_codes) | set(grouped_codes))


async def user_has_permissions(session: AsyncSession, user: User, codes: tuple[str, ...]) -> bool:
    if not codes or user.is_superuser:
        return True
    granted = set(await effective_permission_codes(session, user))
    return all(code in granted for code in codes)
