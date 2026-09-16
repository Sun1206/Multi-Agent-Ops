# 实现内部审计清理及同事务的清理审计记录。

from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from eventwall.models import EventRecord
from rbac.models import User
from rbac.models.authorization import utc_now
from eventwall.selectors import internal_audit_conditions
from eventwall.services import record_event


async def prune_audits(session: AsyncSession, actor: User, request: Request, before_at: datetime) -> int:
    result = await session.execute(delete(EventRecord).where(*internal_audit_conditions(), EventRecord.occurred_at < before_at).execution_options(synchronize_session=False))
    deleted = result.rowcount
    log = await record_event(session, actor=actor, method=request.method, path=request.url.path, ip_address=request.client.host if request.client else '', correlation_id=getattr(request.state, 'correlation_id', ''), action='prune_operation_audit', title='批量删除操作审计', resource_type='operation_audit', resource_id=before_at.isoformat(), metadata={'before_at': before_at.isoformat(), 'deleted': deleted}, category='resource_change', severity='warning')
    # 现有 MySQL DATETIME 仅保存整秒；上取到下一秒，避免同一小数秒截止时间重复清理掉日志。
    log.occurred_at = max(utc_now(), before_at).replace(microsecond=0) + timedelta(seconds=1)
    return deleted
