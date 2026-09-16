# 构造统一的内部审计范围与数据库分页查询。

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from eventwall.models import EventRecord
from eventwall.schemas import AuditFilters


def internal_audit_conditions():
    return (EventRecord.source_type != 'external', EventRecord.category != 'external_event', EventRecord.result != 'rejected')


async def select_audits(session: AsyncSession, filters: AuditFilters) -> tuple[int, list[EventRecord]]:
    conditions = list(internal_audit_conditions())
    for name, column in [('module', EventRecord.module), ('actor', EventRecord.actor_username), ('result', EventRecord.result)]:
        value = getattr(filters, name)
        if value:
            conditions.append(column == value)
    if filters.search:
        columns = (EventRecord.title, EventRecord.summary, EventRecord.detail, EventRecord.resource_name, EventRecord.resource_id, EventRecord.actor_username, EventRecord.actor_display)
        conditions.append(or_(*(column.icontains(filters.search, autoescape=True) for column in columns)))
    if filters.start_at is not None:
        conditions.append(EventRecord.occurred_at >= filters.start_at)
    if filters.end_at is not None:
        conditions.append(EventRecord.occurred_at <= filters.end_at)
    count = await session.scalar(select(func.count()).select_from(EventRecord).where(*conditions)) or 0
    offset = (filters.page - 1) * filters.page_size
    if filters.page > 1 and offset >= count:
        raise HTTPException(status_code=404, detail='当前页不存在。')
    statement = select(EventRecord).where(*conditions).order_by(EventRecord.occurred_at.desc(), EventRecord.id.desc()).offset(offset).limit(filters.page_size)
    return count, list((await session.scalars(statement)).all())
