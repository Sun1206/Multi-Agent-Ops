# 提供现有操作审计页面的读取与批量清理接口。

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.dependencies import SessionDependency, require_permissions
from app.models import User
from app.models.rbac import utc_now
from app.schemas.events import AuditFilters, AuditPage, AuditResponse, PruneRequest, PruneResponse
from app.selectors.events import select_audits
from app.services.operation_audit import prune_audits


router = APIRouter(prefix='/api/events', tags=['操作审计'])
AuditViewer = Annotated[User, Depends(require_permissions('rbac.audit.view'))]
AuditManager = Annotated[User, Depends(require_permissions('rbac.audit.manage'))]


@router.get('/operation_audit/', response_model=AuditPage, description="按用户提交的分页和筛选条件查询内部审计，不返回敏感事件载荷。")
async def operation_audit(request: Request, session: SessionDependency, actor: AuditViewer, filters: Annotated[AuditFilters, Query()]):
    count, rows = await select_audits(session, filters)
    url = request.url.include_query_params(page_size=filters.page_size)
    next_url = str(url.include_query_params(page=filters.page + 1)) if filters.page * filters.page_size < count else None
    previous_url = str(url.include_query_params(page=filters.page - 1)) if filters.page > 1 else None
    return AuditPage(count=count, next=next_url, previous=previous_url, results=[AuditResponse.model_validate(row) for row in rows])


@router.post('/prune_operation_audit/', response_model=PruneResponse, description="清理严格早于截止时间的内部审计，清理与日志原子提交；不接受列表筛选参数。")
async def prune_operation_audit(request: Request, body: PruneRequest, session: SessionDependency, actor: AuditManager):
    if request.query_params:
        raise HTTPException(status_code=422, detail='清理接口不接受查询参数。')
    if body.before_at > utc_now():
        raise HTTPException(status_code=422, detail='截止时间不能晚于当前时间。')
    deleted = await prune_audits(session, actor, request, body.before_at)
    await session.commit()
    return PruneResponse(deleted=deleted, before_at=body.before_at)
