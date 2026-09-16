from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select

from aidevops.dependencies import SessionDependency, require_permissions
from ops.models import AlertAction
from rbac.models import User
from ops.alerts.schemas import AlertActionRequest, AlertCreate, AlertMuteRequest, AlertPatch
from ops.alerts.selectors import action_response, filtered_alerts, get_alert, group_alerts, pagination, project_alerts, summarize
from ops.alerts.services import apply_action, remove_alert, save_alert


router = APIRouter(prefix='/api', tags=['告警事件'])
AlertViewer = Annotated[User, Depends(require_permissions('ops.alert.view'))]
AlertManager = Annotated[User, Depends(require_permissions('ops.alert.manage'))]


# 分页保留所有筛选参数；count是完整匹配数，上一页/下一页使用当前请求URL。
def page_response(request, count, rows, page, size):
    url = request.url.include_query_params(page_size=size)
    return {'count': count, 'next': str(url.include_query_params(page=page + 1)) if page * size < count else None, 'previous': str(url.include_query_params(page=page - 1)) if page > 1 else None, 'results': rows}


# 共享筛选与批量关联投影，读取不会修改告警或自动解除屏蔽。
@router.get('/alerts/', description='分页查询告警事件，支持旧页面筛选和多人认领展示。')
async def list_alerts(request: Request, session: SessionDependency, actor: AlertViewer):
    page, size = pagination(request.query_params)
    statement = await filtered_alerts(session, request.query_params)
    count = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    rows = list((await session.scalars(statement.offset((page - 1) * size).limit(size))).all())
    return page_response(request, count, await project_alerts(session, rows, actor), page, size)


# 静态统计路径先于id注册，统计基于全部筛选结果而不是当前页。
@router.get('/alerts/summary/', description='统计筛选后的告警等级、状态、认领及抑制数量。')
async def alert_summary(request: Request, session: SessionDependency, actor: AlertViewer):
    return await summarize(session, await filtered_alerts(session, request.query_params))


# 分组只读取公开业务维度，沿用旧样例及created_at最新时间语义。
@router.get('/alerts/groups/', description='按业务或标签维度分组告警，输出等级计数及样例。')
async def alert_groups(request: Request, session: SessionDependency, actor: AlertViewer):
    return await group_alerts(session, await filtered_alerts(session, request.query_params), request.query_params.get('group_by', ''))


# 创建仅接收可写业务字段，实体和安全审计在同一事务提交。
@router.post('/alerts/', status_code=201, description='创建告警事件并保存同事务安全审计。')
async def create_alert(body: AlertCreate, request: Request, session: SessionDependency, actor: AlertManager):
    item = await save_alert(session, request, actor, body.model_dump())
    result = (await project_alerts(session, [item], actor, current=True))[0]
    await session.commit()
    return result


# 详情包括多人认领、操作和已有安全通知摘要，不触发外部通知。
@router.get('/alerts/{identifier}/', description='读取告警详情和已有处理记录，不触发外部业务。')
async def alert_detail(identifier: int, session: SessionDependency, actor: AlertViewer):
    return (await project_alerts(session, [await get_alert(session, identifier)], actor))[0]


# PATCH不重置未提交字段，运行状态和认领必须通过专用动作变更。
@router.patch('/alerts/{identifier}/', description='仅编辑显式提交的告警业务字段，保留运行状态。')
async def patch_alert(identifier: int, body: AlertPatch, request: Request, session: SessionDependency, actor: AlertManager):
    item = await save_alert(session, request, actor, body.model_dump(exclude_unset=True), identifier)
    result = (await project_alerts(session, [item], actor, current=True))[0]
    await session.commit()
    return result


# PUT使用创建schema默认值完整更新可写字段，不重置运行字段。
@router.put('/alerts/{identifier}/', description='完整更新告警可写业务字段，不覆盖认领或状态字段。')
async def put_alert(identifier: int, body: AlertCreate, request: Request, session: SessionDependency, actor: AlertManager):
    item = await save_alert(session, request, actor, body.model_dump(), identifier)
    result = (await project_alerts(session, [item], actor, current=True))[0]
    await session.commit()
    return result


# 删除只作用于路径告警及其从属记录，审计一起提交，失败全部回滚。
@router.delete('/alerts/{identifier}/', status_code=204, description='删除指定告警及从属记录，并原子提交安全审计。')
async def delete_alert(identifier: int, request: Request, session: SessionDependency, actor: AlertManager):
    await remove_alert(session, request, actor, identifier)
    await session.commit()
    return Response(status_code=204)


# 装配已实现的人工动作；没有注册升级或通知发送的假成功路径。
def register_action(action, schema):
    # 先获取行锁并执行动作，投影结果和记录准备完成后只提交一次事务。
    async def mutate(identifier: int, body: schema, request: Request, session: SessionDependency, actor: AlertManager):
        item = await apply_action(session, request, actor, identifier, action, body)
        result = (await project_alerts(session, [item], actor, current=True))[0]
        await session.commit()
        return result
    mutate.__name__ = 'alert_' + action
    router.add_api_route('/alerts/{identifier}/' + action + '/', mutate, methods=['POST'], description={'acknowledge': '确认告警，确认与认领保持独立。', 'claim': '当前账号认领告警，支持多人并存与重复认领保护。', 'unclaim': '仅取消当前账号自己的认领，不影响其他处理人。', 'mute': '按指定分钟数手动屏蔽告警，并记录到期时间。', 'resolve': '标记告警已恢复并保存恢复时间。', 'close': '人工关闭告警并保存关闭时间。', 'reopen': '重新打开告警，取消确认和抑制标记，保留认领历史。'}[action])


for action in ('acknowledge', 'claim', 'unclaim', 'mute', 'resolve', 'close', 'reopen'):
    register_action(action, AlertMuteRequest if action == 'mute' else AlertActionRequest)


# 操作记录只读，支持旧alert/action/actor筛选，不允许新增或伪造审计。
@router.get('/alert-actions/', description='分页读取告警操作记录，支持告警、动作及账号筛选。')
async def list_actions(request: Request, session: SessionDependency, actor: AlertViewer):
    page, size = pagination(request.query_params)
    statement = select(AlertAction)
    for name in ('alert', 'action', 'actor'):
        value = request.query_params.get(name)
        if value:
            if name == 'alert':
                try:
                    value = int(value)
                except ValueError:
                    raise HTTPException(422, '告警ID筛选不合法。') from None
            statement = statement.where(getattr(AlertAction, 'alert_id' if name == 'alert' else name) == value)
    count = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = await session.scalars(statement.order_by(AlertAction.created_at.desc(), AlertAction.id.desc()).offset((page - 1) * size).limit(size))
    return page_response(request, count, [action_response(row) for row in rows], page, size)


# 定位单条只读操作记录；错误ID返回404，不从前端载荷恢复记录。
@router.get('/alert-actions/{identifier}/', description='读取单条告警操作记录及中文动作说明。')
async def action_detail(identifier: int, session: SessionDependency, actor: AlertViewer):
    item = await session.get(AlertAction, identifier)
    if item is None:
        raise HTTPException(404, '告警操作记录不存在。')
    return action_response(item)
