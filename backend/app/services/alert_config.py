# 原子维护告警配置、关联关系、渠道密文和安全审计。

import secrets
from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.core.exceptions import BusinessError
from app.models import AlertAggregationRule, AlertEscalationPolicy, AlertIntegration, AlertNotificationChannel, AlertRecipient, AlertRecipientGroup, User
from app.schemas.alert_config import SCHEMAS
from app.selectors.alert_config import ASSOCIATION_TABLES, RESOURCE_MODELS, get_resource
from app.services.config_secrets import ENVELOPE, transform_auth
from app.services.events import is_sensitive_key, record_event


WRITABLE_FIELDS = {
    'alert-integrations': {'name', 'provider', 'is_enabled', 'default_labels', 'description'},
    'alert-recipients': {'name', 'user', 'phone', 'email', 'dingtalk_user_id', 'feishu_user_id', 'wecom_user_id', 'is_enabled', 'description'},
    'alert-recipient-groups': {'name', 'description', 'is_enabled'},
    'alert-notification-channels': {'name', 'channel_type', 'is_enabled', 'send_resolved', 'timeout_seconds', 'config', 'template_title', 'template_body'},
    'alert-notification-rules': {'name', 'is_enabled', 'matchers', 'min_level', 'aggregation_rule', 'escalation_policy', 'notify_on_fire', 'notify_on_resolved', 'notify_on_escalation', 'description'},
    'alert-aggregation-rules': {'name', 'is_enabled', 'matchers', 'group_by', 'window_minutes', 'repeat_interval_minutes', 'description'},
    'alert-inhibition-rules': {'name', 'is_enabled', 'source_matchers', 'target_matchers', 'equal_labels', 'duration_minutes', 'description'},
    # 旧表没有description列；schema仅兼容页面回传，实际持久化字段保持旧模型不变。
    'alert-mute-rules': {'name', 'is_enabled', 'matchers', 'starts_at', 'ends_at', 'reason'},
    'alert-escalation-policies': {'name', 'is_enabled', 'matchers', 'levels', 'repeat_interval_minutes', 'description'},
}

ASSOCIATION_FIELDS = {
    'alert-recipient-groups': {'recipient_ids', 'user_ids'},
    'alert-notification-rules': {'channel_ids', 'recipient_ids', 'recipient_group_ids'},
}

AUDIT_RESOURCE_TYPES = {
    'alert-integrations': 'alert_integration',
    'alert-recipients': 'alert_recipient',
    'alert-recipient-groups': 'alert_recipient_group',
    'alert-notification-channels': 'alert_notification_channel',
    'alert-notification-rules': 'alert_notification_rule',
    'alert-aggregation-rules': 'alert_aggregation_rule',
    'alert-inhibition-rules': 'alert_inhibition_rule',
    'alert-mute-rules': 'alert_mute_rule',
    'alert-escalation-policies': 'alert_escalation_policy',
}


# 审计只记录资源ID和变更字段名，不保存渠道配置、令牌或联系方式原值。
async def audit_config(session, request, actor, action, kind, identifier, fields=()):
    await record_event(session, actor=actor, method=request.method, path=request.url.path, ip_address=request.client.host if request.client else '', correlation_id=getattr(request.state, 'correlation_id', ''), action=action, title='告警配置管理', resource_type=AUDIT_RESOURCE_TYPES[kind], resource_id=str(identifier), metadata={'fields': sorted(fields)}, module='ops', category='alert')


# 生成不可预测且满足数据库长度限制的接入令牌，并对已存在碰撞做有界重试。
async def generate_integration_token(session):
    for _ in range(5):
        token = secrets.token_urlsafe(32)
        if await session.scalar(select(AlertIntegration.id).where(AlertIntegration.token == token)) is None:
            return token
    raise BusinessError('无法生成唯一接入令牌，请稍后重试。')


# URL、webhook地址、headers/env和常规敏感键统一加密，页面掩码仅能保留原路径值。
def protect_channel_config(value, old=None, *, key='', depth=0):
    if depth > 20:
        raise BusinessError('渠道配置嵌套过深。')
    sensitive = is_sensitive_key(key) or key.lower() in {'url', 'webhook_url'}
    if sensitive:
        previous = old
        return transform_auth({'token': value}, {'token': previous} if previous is not None else None)['token']
    if isinstance(value, dict):
        if ENVELOPE in value:
            raise BusinessError('客户端不能提交凭据密文封装。')
        output = {}
        for child, item in value.items():
            previous = old.get(child) if isinstance(old, dict) else None
            if child in {'headers', 'env'}:
                if not isinstance(item, dict):
                    raise BusinessError('headers/env 必须是对象。')
                output[child] = {leaf: transform_auth({'token': raw}, {'token': previous.get(leaf)} if isinstance(previous, dict) and leaf in previous else None)['token'] for leaf, raw in item.items()}
            else:
                output[child] = protect_channel_config(item, previous, key=child, depth=depth + 1)
        return output
    if isinstance(value, list):
        return [protect_channel_config(item, old[index] if isinstance(old, list) and index < len(old) else None, depth=depth + 1) for index, item in enumerate(value)]
    return value


# 读取当前多对多ID，供PATCH保留未提交关系并由完整schema复验最终状态。
async def current_associations(session, kind, identifier):
    output = {}
    mapping = {
        'alert-recipient-groups': {'recipient_ids': 'group_recipients', 'user_ids': 'group_users'},
        'alert-notification-rules': {'channel_ids': 'rule_channels', 'recipient_ids': 'rule_recipients', 'recipient_group_ids': 'rule_groups'},
    }.get(kind, {})
    for field, table_name in mapping.items():
        table = ASSOCIATION_TABLES[table_name]
        output[field] = list((await session.scalars(select(table.c.target_id).where(table.c.source_id == identifier).order_by(table.c.target_id))).all())
    return output


# 将数据库当前值恢复为请求字段名，避免PATCH遗漏字段被默认值覆盖。
async def current_values(session, kind, item):
    values = {}
    for name in WRITABLE_FIELDS[kind]:
        column = {'user': 'user_id', 'aggregation_rule': 'aggregation_rule_id', 'escalation_policy': 'escalation_policy_id'}.get(name, name)
        values[name] = deepcopy(getattr(item, column))
    values.update(await current_associations(session, kind, item.id))
    return values


# 批量验证外键目标存在，并锁定目标行降低并发删除造成的关联竞态。
async def require_ids(session, model, values, label):
    expected = sorted(set(values))
    if not expected:
        return []
    found = sorted((await session.scalars(select(model.id).where(model.id.in_(expected)).with_for_update())).all())
    if found != expected:
        raise BusinessError(f'{label}包含不存在的对象。')
    return expected


# 校验所有外键和JSON中的渠道ID，返回去重排序后的稳定关联值。
async def validate_relationships(session, kind, values):
    if kind == 'alert-recipients' and values.get('user') is not None:
        await require_ids(session, User, [values['user']], '关联账号')
    if kind == 'alert-recipient-groups':
        values['recipient_ids'] = await require_ids(session, AlertRecipient, values['recipient_ids'], '收件人')
        values['user_ids'] = await require_ids(session, User, values['user_ids'], '账号')
    if kind == 'alert-notification-rules':
        values['channel_ids'] = await require_ids(session, AlertNotificationChannel, values['channel_ids'], '通知渠道')
        values['recipient_ids'] = await require_ids(session, AlertRecipient, values['recipient_ids'], '收件人')
        values['recipient_group_ids'] = await require_ids(session, AlertRecipientGroup, values['recipient_group_ids'], '收件人组')
        if values.get('aggregation_rule') is not None:
            await require_ids(session, AlertAggregationRule, [values['aggregation_rule']], '聚合规则')
        if values.get('escalation_policy') is not None:
            await require_ids(session, AlertEscalationPolicy, [values['escalation_policy']], '升级策略')
        if not values['channel_ids']:
            raise BusinessError('通知规则至少需要一个通知渠道。')
    if kind == 'alert-escalation-policies':
        normalized = []
        for level in values['levels']:
            level = dict(level)
            level['channel_ids'] = await require_ids(session, AlertNotificationChannel, level['channel_ids'], '升级渠道')
            normalized.append(level)
        values['levels'] = normalized
    if kind == 'alert-mute-rules':
        starts_at, ends_at = values.get('starts_at'), values.get('ends_at')
        if (starts_at is None) != (ends_at is None) or starts_at is not None and ends_at <= starts_at:
            raise BusinessError('静默开始和结束时间必须同时填写，且结束时间晚于开始时间。')
    return values


# 用完整创建schema校验合并后的最终状态，保证PUT和PATCH遵循同一业务边界。
async def normalized_values(session, kind, submitted, current=None):
    merged = {**(current or {}), **submitted}
    create_schema = SCHEMAS[kind][0]
    validated = create_schema.model_validate(merged).model_dump()
    for name in ASSOCIATION_FIELDS.get(kind, set()):
        validated[name] = sorted(set(validated[name]))
    return await validate_relationships(session, kind, validated)


# 替换单个多对多关系表；删除和新增与主实体及审计共用一个事务。
async def replace_association(session, table, identifier, target_ids):
    await session.execute(delete(table).where(table.c.source_id == identifier))
    if target_ids:
        await session.execute(table.insert(), [{'source_id': identifier, 'target_id': target} for target in target_ids])


# 按资源类型替换前端提交的关联数组，遗漏字段已在合并阶段保留。
async def replace_associations(session, kind, identifier, values):
    mapping = {
        'alert-recipient-groups': {'recipient_ids': 'group_recipients', 'user_ids': 'group_users'},
        'alert-notification-rules': {'channel_ids': 'rule_channels', 'recipient_ids': 'rule_recipients', 'recipient_group_ids': 'rule_groups'},
    }.get(kind, {})
    for field, table_name in mapping.items():
        await replace_association(session, ASSOCIATION_TABLES[table_name], identifier, values[field])


# 创建或更新单项配置；调用方完成安全投影后只提交一次事务。
async def save_resource(session, request, actor, kind, submitted, identifier=None):
    item = await get_resource(session, kind, identifier, lock=True) if identifier is not None else RESOURCE_MODELS[kind]()
    current = await current_values(session, kind, item) if identifier is not None else None
    values = await normalized_values(session, kind, submitted, current)
    if identifier is None and kind == 'alert-integrations':
        item.token = await generate_integration_token(session)
        item.secret = ''
    if identifier is None and kind == 'alert-mute-rules':
        item.created_by = actor.username
    for name in WRITABLE_FIELDS[kind]:
        value = values[name]
        column = {'user': 'user_id', 'aggregation_rule': 'aggregation_rule_id', 'escalation_policy': 'escalation_policy_id'}.get(name, name)
        if kind == 'alert-notification-channels' and name == 'config':
            old = item.config if identifier is not None else None
            value = protect_channel_config(value, old)
        setattr(item, column, value)
    if identifier is None:
        session.add(item)
    await session.flush()
    await replace_associations(session, kind, item.id, values)
    await session.flush()
    fields = set(submitted) & (WRITABLE_FIELDS[kind] | ASSOCIATION_FIELDS.get(kind, set()))
    await audit_config(session, request, actor, 'create_alert_config' if identifier is None else 'update_alert_config', kind, item.id, fields)
    return item


# 删除配置行并依靠已声明的SET NULL/CASCADE约束保护告警和日志业务记录。
async def remove_resource(session, request, actor, kind, identifier):
    item = await get_resource(session, kind, identifier, lock=True)
    if kind == 'alert-notification-channels':
        table = ASSOCIATION_TABLES['rule_channels']
        referenced_rule = await session.scalar(select(table.c.source_id).where(table.c.target_id == identifier).limit(1).with_for_update())
        policies = list((await session.scalars(select(AlertEscalationPolicy).with_for_update())).all())
        referenced_policy = any(identifier in level.get('channel_ids', []) for policy in policies if isinstance(policy.levels, list) for level in policy.levels if isinstance(level, dict))
        if referenced_rule is not None or referenced_policy:
            raise HTTPException(409, '通知渠道仍被通知规则或升级策略引用，请先解除关联。')
    await session.delete(item)
    await session.flush()
    await audit_config(session, request, actor, 'delete_alert_config', kind, identifier)
