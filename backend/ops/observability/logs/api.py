from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from aidevops.dependencies import SessionDependency, require_any_permission, require_permissions
from ops.observability.logs.config_service import remove_data_source, save_data_source
from ops.observability.logs.runtime import catalog, query, test_connection
from ops.observability.logs.schemas import LogCatalogRequest, LogDataSourceWrite, LogQuery
from ops.observability.logs.selectors import filtered_data_sources, project_data_source
from rbac.models import User
from rbac.selectors.permissions import user_has_permissions


router = APIRouter(prefix="/api/log", tags=["日志中心"])
LogChooser = Annotated[User, Depends(require_any_permission("ops.log.query", "ops.log.datasource.view"))]
LogManager = Annotated[User, Depends(require_permissions("ops.log.datasource.manage"))]
LogQuerier = Annotated[User, Depends(require_permissions("ops.log.query"))]


@router.get("/providers/", description="查询日志数据源供应商及页面默认配置。")
async def providers(actor: LogChooser):
    return {"providers": [
        {"id": "loki", "name": "Loki", "capabilities": {"catalog": ["labels", "label_values"], "query": True, "test_connection": True}, "defaults": {"endpoint": ""}},
        {"id": "elk", "name": "ELK / Elasticsearch", "capabilities": {"catalog": ["sources"], "query": True, "test_connection": True}, "defaults": {"endpoint": "", "auth_type": "none", "index_pattern": "logs-*", "time_field": "@timestamp", "message_fields": "message,log,msg"}},
        {"id": "sls", "name": "阿里云 SLS", "capabilities": {"catalog": ["sources"], "query": True, "test_connection": True}, "defaults": {"endpoint": "", "project": "", "logstore": "", "topic": "", "access_key_id": "configured", "access_key_secret": "configured"}},
    ]}


@router.get("/datasources/", description="查询日志数据源列表并按权限隐藏连接配置。")
async def list_sources(request: Request, session: SessionDependency, actor: LogChooser):
    rows = list((await session.scalars(filtered_data_sources(request.query_params))).all())
    include = await user_has_permissions(session, actor, ("ops.log.datasource.view",))
    return [project_data_source(item, include_config=include) for item in rows]


@router.post("/datasources/", status_code=201, description="创建日志数据源并加密保存凭据。")
async def create_source(body: LogDataSourceWrite, request: Request, session: SessionDependency, actor: LogManager):
    item = await save_data_source(session, request, actor, body.model_dump())
    result = project_data_source(item, include_config=True)
    await session.commit()
    return result


@router.put("/datasources/{identifier}/", description="完整更新日志数据源及连接配置。")
async def update_source(identifier: int, body: LogDataSourceWrite, request: Request, session: SessionDependency, actor: LogManager):
    item = await save_data_source(session, request, actor, body.model_dump(), identifier)
    result = project_data_source(item, include_config=True)
    await session.commit()
    return result


@router.delete("/datasources/{identifier}/", status_code=204, description="删除日志数据源。")
async def delete_source(identifier: int, request: Request, session: SessionDependency, actor: LogManager):
    await remove_data_source(session, request, actor, identifier)
    await session.commit()
    return Response(status_code=204)


@router.post("/providers/{provider}/catalog/", description="读取日志数据源目录。")
async def log_catalog(provider: str, body: LogCatalogRequest, request: Request, session: SessionDependency, actor: LogQuerier):
    actor_id = actor.id
    await session.rollback()
    return await catalog(request.app.state.session_factory, actor_id, provider, request, body)


@router.post("/datasources/{identifier}/test_connection/", description="测试日志数据源连接。")
async def test_log_source(identifier: int, request: Request, session: SessionDependency, actor: LogManager):
    actor_id = actor.id
    await session.rollback()
    return await test_connection(request.app.state.session_factory, actor_id, request, identifier)


@router.post("/query/", description="查询日志数据源并返回统一格式的日志结果。")
async def query_logs(body: LogQuery, request: Request, session: SessionDependency, actor: LogQuerier):
    actor_id = actor.id
    await session.rollback()
    return await query(request.app.state.session_factory, actor_id, request, body)
