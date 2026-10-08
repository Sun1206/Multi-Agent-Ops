from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from aidevops.dependencies import SessionDependency, require_permissions
from aiops.schemas.audit import AuditRange, AuditListFilters, AuditDeleteInput
from aiops.selectors.audit import build_costs, build_overview
from aiops.selectors.audit_details import list_details
from aiops.services.audit import delete_details
from rbac.models import User


router = APIRouter(prefix='/api/aiops/admin/audit', tags=['AIOps运行概览'])
AuditViewer = Annotated[User, Depends(require_permissions('aiops.audit.view'))]
AuditManager = Annotated[User, Depends(require_permissions('aiops.audit.manage'))]


def audit_range(
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
    start: datetime | None = None,
    end: datetime | None = None,
    range: Literal['all'] | None = None,
) -> AuditRange:
    try:
        return AuditRange(days=days, start=start, end=end, range=range)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


AuditFilters = Annotated[AuditRange, Depends(audit_range)]


@router.get('/overview/', description='按时间范围读取工具、Skill 与 Action 的真实调用分布。')
async def get_overview(session: SessionDependency, actor: AuditViewer, filters: AuditFilters):
    return await build_overview(session, filters.resolve())


@router.get('/costs/', description='按时间范围汇总模型 Token、费用、耗时和工具调用。')
async def get_costs(session: SessionDependency, actor: AuditViewer, filters: AuditFilters):
    return await build_costs(session, filters.resolve())


# 为六个审计页签注册固定路径，保持现有前端方法、请求字段和分页结构。
def register_detail_routes(kind, label, batch_field=None, single_delete=False):
    # 全局审计读取需要独立查看权限；仅输出服务端定义的安全投影。
    async def list_rows(request: Request, session: SessionDependency, actor: AuditViewer, filters: Annotated[AuditListFilters, Query()]):
        return await list_details(session, request, kind, filters)

    list_rows.__name__ = 'list_audit_' + kind.replace('-', '_')
    router.add_api_route('/' + kind + '/', list_rows, methods=['GET'], description=f'分页查询{label}，支持时间及业务字段筛选并隐藏原始敏感载荷。')
    if batch_field:
        # 所有目标验证通过后才提交删除与审计，禁止跨类型批量载荷。
        async def bulk_delete(body: AuditDeleteInput, request: Request, session: SessionDependency, actor: AuditManager):
            identifiers = getattr(body, batch_field)
            if identifiers is None:
                raise HTTPException(422, f'请提供{batch_field}。')
            result = await delete_details(session, request, actor, kind, identifiers)
            await session.commit()
            return result

        bulk_delete.__name__ = 'bulk_delete_audit_' + kind.replace('-', '_')
        router.add_api_route('/' + kind + '/bulk-delete/', bulk_delete, methods=['POST'], description=f'批量清理指定{label}，正在运行的记录不允许删除。')
    if single_delete:
        # 单条清理复用批量服务的事务和运行状态检查，成功返回无正文响应。
        async def remove_row(identifier: int, request: Request, session: SessionDependency, actor: AuditManager):
            if identifier <= 0:
                raise HTTPException(422, '记录编号必须为正整数。')
            await delete_details(session, request, actor, kind, [identifier])
            await session.commit()
            return Response(status_code=204)

        remove_row.__name__ = 'delete_audit_' + kind.replace('-', '_')
        router.add_api_route('/' + kind + '/{identifier}/', remove_row, methods=['DELETE'], status_code=204, description=f'清理指定{label}并保存同事务操作审计。')


for resource, label, batch_field, single_delete in (
    ('sessions', '会话历史', 'session_ids', True),
    ('tool-invocations', '工具调用', 'invocation_ids', True),
    ('model-invocations', '模型调用', None, True),
    ('actions', '待执行动作', 'action_ids', True),
    ('skill-traces', 'Skill命中记录', 'trace_ids', False),
    ('action-traces', 'Action命中记录', 'trace_ids', False),
):
    register_detail_routes(resource, label, batch_field, single_delete)
