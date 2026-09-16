from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rbac.models import PermissionDefinition, Role
from rbac.registry import BUILTIN_ROLES, PERMISSION_DEFINITIONS


async def sync_rbac(session: AsyncSession) -> None:
    permissions = {
        item.code: item for item in (await session.scalars(select(PermissionDefinition))).all()
    }
    for sort_order, (code, name, category, description) in enumerate(PERMISSION_DEFINITIONS, start=1):
        permission = permissions.get(code)
        if permission is None:
            permission = PermissionDefinition(code=code)
            session.add(permission)
            permissions[code] = permission
        permission.name = name
        permission.category = category
        permission.description = description
        permission.sort_order = sort_order
        permission.is_builtin = True
    await session.flush()

    roles = {
        item.code: item
        for item in (await session.scalars(select(Role).options(selectinload(Role.permissions)))).all()
    }
    for definition in BUILTIN_ROLES:
        role = roles.get(definition["code"])
        if role is None:
            role = Role(code=definition["code"])
            session.add(role)
        role.name = definition["name"]
        role.description = definition["description"]
        role.is_builtin = True
        codes = permissions.keys() if "*" in definition["permissions"] else definition["permissions"]
        role.permissions = [permissions[code] for code in codes if code in permissions]
    await session.flush()
