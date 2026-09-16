# 共享账号响应和批量有效权限构造，避免服务依赖路由。

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rbac.models import PermissionDefinition, User
from rbac.models.authorization import group_roles, group_users, role_permissions, user_roles
from rbac.schemas.auth import UserResponse


async def permission_map(session: AsyncSession, users: list[User]) -> dict[int, list[str]]:
    ids = [user.id for user in users]
    result = {user_id: set() for user_id in ids}
    if not ids:
        return {}
    direct = select(user_roles.c.user_id, PermissionDefinition.code).join(role_permissions, role_permissions.c.permission_id == PermissionDefinition.id).join(user_roles, user_roles.c.role_id == role_permissions.c.role_id).where(user_roles.c.user_id.in_(ids))
    grouped = select(group_users.c.user_id, PermissionDefinition.code).join(role_permissions, role_permissions.c.permission_id == PermissionDefinition.id).join(group_roles, group_roles.c.role_id == role_permissions.c.role_id).join(group_users, group_users.c.group_id == group_roles.c.group_id).where(group_users.c.user_id.in_(ids))
    for user_id, code in (await session.execute(direct.union(grouped))).all():
        result[user_id].add(code)
    if any(user.is_superuser for user in users):
        all_codes = set((await session.scalars(select(PermissionDefinition.code))).all())
        for user in users:
            if user.is_superuser:
                result[user.id] = all_codes
    return {user_id: sorted(codes) for user_id, codes in result.items()}


def user_response(user: User, permissions: list[str]) -> UserResponse:
    return UserResponse(id=user.id, username=user.username, email=user.email, first_name=user.first_name, last_name=user.last_name, is_active=user.is_active, is_staff=user.is_staff, is_superuser=user.is_superuser, date_joined=user.date_joined, last_login=user.last_login, roles=sorted(user.roles, key=lambda item: item.id), user_groups=sorted(user.groups, key=lambda item: item.id), effective_permissions=permissions, display_name=user.display_name, is_demo_account=False)


async def serialize_user(session: AsyncSession, user: User) -> UserResponse:
    return user_response(user, (await permission_map(session, [user]))[user.id])
