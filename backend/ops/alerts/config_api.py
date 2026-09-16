# 提供告警配置CRUD和只读通知日志接口，不发送通知或执行规则。

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select

from aidevops.dependencies import SessionDependency, require_permissions
from ops.alerts.api import page_response
from ops.models import AlertNotificationLog
from rbac.models import User
from ops.alerts.config_schemas import SCHEMAS
from ops.alerts.config_selectors import filtered_notification_logs, filtered_resources, get_resource, project_notification_logs, project_resources
from ops.alerts.selectors import pagination
from rbac.selectors.permissions import user_has_permissions
from ops.alerts.config_services import remove_resource, save_resource


router = APIRouter(prefix='/api', tags=['告警配置'])
ConfigViewer = Annotated[User, Depends(require_permissions('ops.alert.config.view'))]
ConfigManager = Annotated[User, Depends(require_permissions('ops.alert.config.manage'))]
AlertViewer = Annotated[User, Depends(require_permissions('ops.alert.view'))]


# 为九类同构资源装配分页、详情、创建、完整更新、局部更新和删除路由。
def register_resource_routes(kind, create_schema, patch_schema):
    root = '/' + kind + '/'

    # 分页查询公开配置，关联对象批量装配且渠道秘密始终脱敏。
    async def list_items(request: Request, session: SessionDependency, actor: ConfigViewer):
        page, size = pagination(request.query_params)
        statement = filtered_resources(kind, request.query_params)
        count = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
        rows = list((await session.scalars(statement.offset((page - 1) * size).limit(size))).all())
        return page_response(request, count, await project_resources(session, kind, rows), page, size)

    # 创建仅应用schema声明的字段，配置、关联和审计同事务提交。
    async def create_item(body: create_schema, request: Request, session: SessionDependency, actor: ConfigManager):
        item = await save_resource(session, request, actor, kind, body.model_dump())
        can_view = await user_has_permissions(session, actor, ('ops.alert.config.view',))
        result = (await project_resources(session, kind, [item], include_integration_url=can_view))[0]
        await session.commit()
        return result

    # 详情读取当前数据库状态，不触发通知、规则计算或外部连接。
    async def detail_item(identifier: int, session: SessionDependency, actor: ConfigViewer):
        return (await project_resources(session, kind, [await get_resource(session, kind, identifier)]))[0]

    # PUT完整更新全部可写字段，页面回传的展示字段已在schema层忽略。
    async def put_item(identifier: int, body: create_schema, request: Request, session: SessionDependency, actor: ConfigManager):
        item = await save_resource(session, request, actor, kind, body.model_dump(), identifier)
        can_view = await user_has_permissions(session, actor, ('ops.alert.config.view',))
        result = (await project_resources(session, kind, [item], include_integration_url=can_view))[0]
        await session.commit()
        return result

    # PATCH只覆盖显式提交字段，遗漏的普通字段、关联和密文保持原值。
    async def patch_item(identifier: int, body: patch_schema, request: Request, session: SessionDependency, actor: ConfigManager):
        values = body.model_dump(exclude_unset=True)
        item = await save_resource(session, request, actor, kind, values, identifier)
        can_view = await user_has_permissions(session, actor, ('ops.alert.config.view',))
        result = (await project_resources(session, kind, [item], include_integration_url=can_view))[0]
        await session.commit()
        return result

    # 删除目标配置并保存同事务审计，外键约束保留告警和通知日志主体。
    async def delete_item(identifier: int, request: Request, session: SessionDependency, actor: ConfigManager):
        await remove_resource(session, request, actor, kind, identifier)
        await session.commit()
        return Response(status_code=204)

    descriptions = {
        'list': '分页查询告警配置，支持名称搜索和常用状态筛选。',
        'create': '创建告警配置并原子保存关联与安全审计。',
        'detail': '读取指定告警配置及前端所需关联信息。',
        'put': '完整更新告警配置的全部可写字段。',
        'patch': '局部更新显式提交的告警配置字段。',
        'delete': '删除指定告警配置并保留相关业务主体记录。',
    }
    routes = [
        (list_items, root, 'GET', 200, 'list'),
        (create_item, root, 'POST', 201, 'create'),
        (detail_item, root + '{identifier}/', 'GET', 200, 'detail'),
        (put_item, root + '{identifier}/', 'PUT', 200, 'put'),
        (patch_item, root + '{identifier}/', 'PATCH', 200, 'patch'),
        (delete_item, root + '{identifier}/', 'DELETE', 204, 'delete'),
    ]
    for function, path, method, status_code, action in routes:
        function.__name__ = kind.replace('-', '_') + '_' + action
        router.add_api_route(path, function, methods=[method], status_code=status_code, description=descriptions[action])


for resource_kind, models in SCHEMAS.items():
    register_resource_routes(resource_kind, *models)


# 通知日志列表只读，过滤结果不包含请求载荷、远端响应和原始错误文本。
@router.get('/alert-notification-logs/', description='分页查询安全脱敏后的告警通知日志。')
async def list_notification_logs(request: Request, session: SessionDependency, actor: AlertViewer):
    page, size = pagination(request.query_params)
    statement = await filtered_notification_logs(session, request.query_params)
    count = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    rows = list((await session.scalars(statement.offset((page - 1) * size).limit(size))).all())
    return page_response(request, count, await project_notification_logs(session, rows), page, size)


# 单条通知日志详情沿用安全投影，不恢复被隐藏的历史请求或响应内容。
@router.get('/alert-notification-logs/{identifier}/', description='读取单条安全脱敏后的告警通知日志。')
async def notification_log_detail(identifier: int, session: SessionDependency, actor: AlertViewer):
    item = await session.get(AlertNotificationLog, identifier)
    if item is None:
        raise HTTPException(404, '告警通知日志不存在。')
    return (await project_notification_logs(session, [item]))[0]
