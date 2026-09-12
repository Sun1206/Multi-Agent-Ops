"""集中实现用户管理的权限边界和最后可用管理员保护。"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.models import Role, User, UserGroup
from app.services.user_serialization import permission_map


async def lock_superusers(session: AsyncSession) -> list[User]:
    """按固定 ID 顺序锁定超级管理员，用当前读避免并发移除最后启用账号。"""
    statement = select(User).where(User.is_superuser.is_(True)).order_by(User.id).with_for_update().execution_options(populate_existing=True)
    return list((await session.scalars(statement)).all())


def protect_last_admin(admins: list[User], target: User, data: dict, *, deleting: bool = False) -> None:
    """拒绝删除、禁用或降级最后一个启用超级管理员，不影响普通账号。"""
    loses_access = deleting or data.get("is_active") is False or data.get("is_superuser") is False
    if target.is_superuser and target.is_active and loses_access:
        if not any(user.id != target.id and user.is_active for user in admins):
            raise BusinessError("至少需要保留一个启用的超级管理员。")


def protect_identity(actor: User, target: User | None, data: dict) -> None:
    """仅超级管理员可修改身份标记或管理超级管理员账号，允许同值表单字段。"""
    if actor.is_superuser:
        return
    if target is not None and target.is_superuser:
        raise HTTPException(403, detail="只有超级管理员可以管理超级管理员账号。")
    for field in ("is_staff", "is_superuser"):
        existing = getattr(target, field) if target is not None else False
        if field in data and data[field] != existing:
            raise HTTPException(403, detail="只有超级管理员可以修改系统身份。")


async def require_permission_subset(session: AsyncSession, actor: User, codes: set[str]) -> None:
    """拒绝普通管理员操作或授予超出自身实时有效权限的权限集合。"""
    if actor.is_superuser:
        return
    own = set((await permission_map(session, [actor]))[actor.id])
    if not codes <= own:
        raise HTTPException(403, detail="不能管理或授予超出自身范围的权限。")


def role_codes(roles: list[Role]) -> set[str]:
    """汇总已预加载角色中的权限编码，供传递授权检查使用。"""
    return {permission.code for role in roles for permission in role.permissions}


async def check_users_boundary(session: AsyncSession, actor: User, users: list[User]) -> None:
    """批量检查受影响成员的已有权限，防止通过组关系管理更高权限账号。"""
    if actor.is_superuser or not users:
        return
    if any(user.is_superuser for user in users):
        raise HTTPException(403, detail="不能通过关系修改超级管理员账号。")
    mappings = await permission_map(session, users)
    await require_permission_subset(session, actor, {code for codes in mappings.values() for code in codes})


async def check_user_relations(session: AsyncSession, actor: User, *, roles: list[Role], groups: list[UserGroup]) -> None:
    """同时检查直属和用户组角色，封堵角色/组绑定的间接提权路径。"""
    await require_permission_subset(session, actor, role_codes(roles) | role_codes([role for group in groups for role in group.roles]))


def protect_builtin(obj: Role | UserGroup, data: dict, *, deleting: bool = False) -> None:
    """禁止删除内置对象或更改其稳定编码，保留同值提交兼容性。"""
    if obj.is_builtin and (deleting or ("code" in data and data["code"] != obj.code)):
        raise BusinessError("内置角色或用户组不能删除或修改编码。")
