# 提供指标数据源 CRUD；远端连接与 PromQL 运行路由在运行服务就绪后装配。

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from aidevops.dependencies import SessionDependency, require_any_permission, require_permissions
from rbac.models import User
from ops.observability.metrics.schemas import MetricConnectionTest, MetricDataSourceCreate, MetricDataSourcePatch, MetricQuery, MetricSeriesNames
from ops.observability.metrics.selectors import filtered_data_sources, get_data_source, project_data_source
from rbac.selectors.permissions import user_has_permissions
from ops.observability.metrics.config_service import remove_data_source, save_data_source
from ops.observability.metrics.runtime import execute_metric_query, list_metric_names, test_metric_connection


router = APIRouter(prefix="/api/observability", tags=["指标查询"])
MetricChooser = Annotated[
    User,
    Depends(require_any_permission("ops.metric.query", "ops.metric.datasource.view")),
]
MetricViewer = Annotated[User, Depends(require_permissions("ops.metric.datasource.view"))]
MetricManager = Annotated[User, Depends(require_permissions("ops.metric.datasource.manage"))]
MetricQuerier = Annotated[User, Depends(require_permissions("ops.metric.query"))]


# 判断当前管理者是否同时拥有配置查看权限，以选择完整或精简响应。
async def manager_can_view(session: AsyncSession, actor: User) -> bool:
    return await user_has_permissions(session, actor, ("ops.metric.datasource.view",))


# 查询数据源列表；query-only 用户仅获得安全下拉字段。
@router.get("/metric/datasources/", description="查询指标数据源列表，并按权限隐藏连接配置。")
async def list_metric_data_sources(request: Request, session: SessionDependency, actor: MetricChooser):
    rows = list((await session.scalars(filtered_data_sources(request.query_params))).all())
    include_config = await user_has_permissions(session, actor, ("ops.metric.datasource.view",))
    return [project_data_source(item, include_config=include_config) for item in rows]


# 创建指标数据源，原子保存兼容密文、默认项调整和安全审计。
@router.post("/metric/datasources/", status_code=201, description="创建指标数据源并安全保存连接配置。")
async def create_metric_data_source(
    body: MetricDataSourceCreate,
    request: Request,
    session: SessionDependency,
    actor: MetricManager,
):
    item = await save_data_source(session, request, actor, body.model_dump())
    result = project_data_source(item, include_config=await manager_can_view(session, actor))
    await session.commit()
    return result


# 读取指定指标数据源的完整脱敏配置，不触发远端连接。
@router.get("/metric/datasources/{identifier}/", description="读取指定指标数据源的脱敏配置。")
async def get_metric_data_source(identifier: int, session: SessionDependency, actor: MetricViewer):
    return project_data_source(await get_data_source(session, identifier), include_config=True)


# 完整更新数据源字段，页面掩码只保留同路径已有秘密。
@router.put("/metric/datasources/{identifier}/", description="完整更新指标数据源配置。")
async def put_metric_data_source(
    identifier: int,
    body: MetricDataSourceCreate,
    request: Request,
    session: SessionDependency,
    actor: MetricManager,
):
    item = await save_data_source(session, request, actor, body.model_dump(), identifier)
    result = project_data_source(item, include_config=await manager_can_view(session, actor))
    await session.commit()
    return result


# 局部更新显式提交字段，遗漏字段和已有密文保持不变。
@router.patch("/metric/datasources/{identifier}/", description="局部更新指标数据源配置。")
async def patch_metric_data_source(
    identifier: int,
    body: MetricDataSourcePatch,
    request: Request,
    session: SessionDependency,
    actor: MetricManager,
):
    values = body.model_dump(exclude_unset=True)
    item = await save_data_source(session, request, actor, values, identifier, partial=True)
    result = project_data_source(item, include_config=await manager_can_view(session, actor))
    await session.commit()
    return result


# 删除指定数据源及同事务审计，不级联删除其他业务主体。
@router.delete("/metric/datasources/{identifier}/", status_code=204, description="删除指定指标数据源。")
async def delete_metric_data_source(
    identifier: int,
    request: Request,
    session: SessionDependency,
    actor: MetricManager,
):
    await remove_data_source(session, request, actor, identifier)
    await session.commit()
    return Response(status_code=204)


# 测试指定数据源的即时查询连接，网络阶段不持有请求数据库事务。
@router.post("/metric/datasources/{identifier}/test_connection/", description="测试指标数据源连接并返回安全摘要。")
async def test_metric_data_source(
    identifier: int,
    body: MetricConnectionTest,
    request: Request,
    session: SessionDependency,
    actor: MetricManager,
):
    actor_id = actor.id
    await session.rollback()
    return await test_metric_connection(request.app.state.session_factory, actor_id, request, identifier, body)


# 查询 Prometheus 指标名并提供去重排序后的补全候选。
@router.get("/metrics/series-names/", description="查询指标名补全候选。")
async def list_metric_series_names(request: Request, session: SessionDependency, actor: MetricQuerier):
    try:
        params = MetricSeriesNames.model_validate(dict(request.query_params))
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from None
    actor_id = actor.id
    await session.rollback()
    return await list_metric_names(request.app.state.session_factory, actor_id, request, params)


# 执行即时或区间 PromQL 查询并返回前端图表兼容结果。
@router.post("/metrics/query/", description="执行 PromQL 指标查询并返回图表数据。")
async def query_metrics(
    body: MetricQuery,
    request: Request,
    session: SessionDependency,
    actor: MetricQuerier,
):
    actor_id = actor.id
    await session.rollback()
    return await execute_metric_query(request.app.state.session_factory, actor_id, request, body)
