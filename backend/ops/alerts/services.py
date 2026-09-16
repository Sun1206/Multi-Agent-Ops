from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select

from ops.models import Alert, AlertAction, AlertClaim, AlertIntegration, Host
from rbac.models.authorization import utc_now
from ops.alerts.selectors import get_alert
from eventwall import services as events


# 使用既有同事务审计，只记录ID、动作和字段名，不保存原始告警或通知载荷。
async def audit_alert(session, request, actor, action, identifier, fields=()):
    await events.record_event(session, actor=actor, method=request.method, path=request.url.path, ip_address=request.client.host if request.client else '', correlation_id=getattr(request.state, 'correlation_id', ''), action=action, title='告警事件管理', resource_type='alert', resource_id=str(identifier), metadata={'fields': list(fields)}, module='ops', category='alert')


# 关联对象必须存在；验证只读取元数据，不触发接入源或主机连接。
async def validate_links(session, values):
    for name, model in [('host', Host), ('integration', AlertIntegration)]:
        if values.get(name) is not None and await session.get(model, values[name]) is None:
            raise HTTPException(400, '告警关联对象不存在。')


# 创建与编辑仅应用schema可写字段，运行状态由专用动作管理；调用方负责唯一提交。
async def save_alert(session, request, actor, values, identifier=None):
    item = await get_alert(session, identifier, lock=True) if identifier is not None else Alert()
    await validate_links(session, values)
    for name, value in values.items():
        setattr(item, name + '_id' if name in ('host', 'integration') else name, value)
    if identifier is None:
        session.add(item)
    await session.flush()
    await audit_alert(session, request, actor, 'create_alert' if identifier is None else 'update_alert', item.id, values.keys())
    return item


# 先锁定目标后删除，现有CASCADE外键清理从属记录；审计不会与删除分开提交。
async def remove_alert(session, request, actor, identifier):
    item = await get_alert(session, identifier, lock=True)
    await session.delete(item)
    await session.flush()
    await audit_alert(session, request, actor, 'delete_alert', identifier)


# 行锁串行化同告警动作；认领可多人并存，取消只删除当前账号自己的记录。
async def apply_action(session, request, actor, identifier, action, body):
    item = await get_alert(session, identifier, lock=True)
    now = utc_now()
    if action == 'acknowledge':
        item.is_acknowledged, item.acknowledged_by, item.acknowledged_at = True, actor.username, now
    elif action in ('claim', 'unclaim'):
        if action == 'claim':
            # MySQL默认可重复读下使用当前读，避免认证时建立的旧快照看不到其他人新认领。
            existing = await session.scalar(select(AlertClaim.id).where(AlertClaim.alert_id == identifier, AlertClaim.claimant == actor.username).with_for_update())
            if existing is None:
                session.add(AlertClaim(alert_id=identifier, claimant=actor.username, claimed_at=now))
        else:
            await session.execute(delete(AlertClaim).where(AlertClaim.alert_id == identifier, AlertClaim.claimant == actor.username))
        await session.flush()
        first = await session.scalar(select(AlertClaim).where(AlertClaim.alert_id == identifier).order_by(AlertClaim.claimed_at, AlertClaim.id).with_for_update())
        item.claimed_by, item.claimed_at = (first.claimant, first.claimed_at) if first else ('', None)
    elif action == 'mute':
        until = now + timedelta(minutes=body.minutes)
        item.status, item.is_suppressed, item.suppressed_by = 'muted', True, 'manual_mute'
        item.suppressed_until = item.mute_until = until
        item.muted_by, item.muted_reason = actor.username, body.note or f'屏蔽 {body.minutes} 分钟'
    elif action == 'resolve':
        item.status, item.ends_at = 'resolved', now
    elif action == 'close':
        item.status, item.closed_at = 'closed', now
    elif action == 'reopen':
        item.status, item.closed_at, item.ends_at = 'active', None, None
        item.is_acknowledged = item.is_suppressed = False
    else:
        raise HTTPException(400, '告警动作未实现。')
    item.updated_at = now
    session.add(AlertAction(alert_id=identifier, action=action, actor=actor.username, note=body.note, metadata_data={}))
    await session.flush()
    await audit_alert(session, request, actor, action, identifier)
    return item
