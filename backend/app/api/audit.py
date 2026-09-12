"""汇总用户管理请求审计上下文，保证业务与审计一起提交。"""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.events import record_event


async def audit_and_commit(session: AsyncSession, request: Request, actor: User, *, action: str, resource_type: str, resource_id: int, fields: list[str], data: dict | None = None) -> None:
    """只记录字段名和白名单关系 ID，业务与脱敏审计一起提交，失败一并回滚。"""
    relations = {name: sorted(set(values)) for name, values in (data or {}).items() if name in {"role_ids", "group_ids", "user_ids", "permission_ids"}}
    titles = {"create_user": "创建用户", "update_user": "修改用户", "delete_user": "删除用户", "reset_user_password": "重置用户密码", "create_role": "创建角色", "update_role": "修改角色", "delete_role": "删除角色", "create_group": "创建用户组", "update_group": "修改用户组", "delete_group": "删除用户组"}
    await record_event(session, actor=actor, method=request.method, path=request.url.path, ip_address=request.client.host if request.client else "", correlation_id=getattr(request.state, "correlation_id", ""), action=action, title=titles.get(action, action), resource_type=resource_type, resource_id=str(resource_id), metadata={"changed_fields": sorted(fields), "relations": relations})
    await session.commit()
