# 查询告警配置及关联对象，并投影为旧前端可直接使用的安全结构。

from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import delete, func, inspect, or_, select

from aidevops.database import Base
from ops.models import AlertAggregationRule, AlertEscalationPolicy, AlertInhibitionRule, AlertIntegration, AlertMuteRule, AlertNotificationChannel, AlertNotificationLog, AlertNotificationRule, AlertRecipient, AlertRecipientGroup
from rbac.models import User
from aidevops.config_secrets import ENVELOPE, transform_auth
from eventwall.services import is_sensitive_key


RESOURCE_MODELS = {
    'alert-integrations': AlertIntegration,
    'alert-recipients': AlertRecipient,
    'alert-recipient-groups': AlertRecipientGroup,
    'alert-notification-channels': AlertNotificationChannel,
    'alert-notification-rules': AlertNotificationRule,
    'alert-aggregation-rules': AlertAggregationRule,
    'alert-inhibition-rules': AlertInhibitionRule,
    'alert-mute-rules': AlertMuteRule,
    'alert-escalation-policies': AlertEscalationPolicy,
}

SEARCH_FIELDS = {
    kind: tuple(name for name in ('name', 'description', 'provider', 'channel_type', 'email', 'phone', 'reason') if hasattr(model, name))
    for kind, model in RESOURCE_MODELS.items()
}

ASSOCIATION_TABLES = {
    'group_recipients': Base.metadata.tables['ops_alertrecipientgroup_recipients'],
    'group_users': Base.metadata.tables['ops_alertrecipientgroup_users'],
    'rule_channels': Base.metadata.tables['ops_alertnotificationrule_channels'],
    'rule_recipients': Base.metadata.tables['ops_alertnotificationrule_recipients'],
    'rule_groups': Base.metadata.tables['ops_alertnotificationrule_recipient_groups'],
}


# 用户轻量结构与旧序列化器保持一致，不包含权限、密码或令牌信息。
def user_lite(user):
    return {'id': user.id, 'username': user.username, 'email': user.email, 'first_name': user.first_name, 'last_name': user.last_name, 'display_name': user.display_name}


# 只返回模型列，外键字段转换为旧序列化器使用的无_id名称。
def public_columns(item):
    result = {column.key: getattr(item, column.key) for column in inspect(type(item)).column_attrs}
    result.pop('token', None)
    result.pop('secret', None)
    aliases = {'user_id': 'user', 'aggregation_rule_id': 'aggregation_rule', 'escalation_policy_id': 'escalation_policy'}
    for name, alias in aliases.items():
        if name in result:
            result[alias] = result.pop(name)
    return result


# 对渠道配置递归脱敏；URL类字段即使不含token/secret也按凭据处理。
def masked_channel_config(value, *, key=''):
    if is_sensitive_key(key) or key.lower() in {'url', 'webhook_url'}:
        return '***' if value else ''
    if isinstance(value, dict):
        if ENVELOPE in value:
            return '***'
        return {child: masked_channel_config(item, key=child) for child, item in value.items()}
    if isinstance(value, list):
        return [masked_channel_config(item) for item in value]
    return value


# 读取单条配置；写入流程可申请行锁并强制刷新当前数据库状态。
async def get_resource(session, kind, identifier, *, lock=False):
    model = RESOURCE_MODELS[kind]
    statement = select(model).where(model.id == identifier).execution_options(populate_existing=True)
    if lock:
        statement = statement.with_for_update()
    item = await session.scalar(statement)
    if item is None:
        raise HTTPException(404, '告警配置不存在。')
    return item


# 构造稳定倒序列表查询，并支持旧页面常用搜索和简单精确筛选。
def filtered_resources(kind, params):
    model = RESOURCE_MODELS[kind]
    statement = select(model)
    term = (params.get('search') or '').strip()
    fields = SEARCH_FIELDS[kind]
    if term and fields:
        statement = statement.where(or_(*[getattr(model, name).icontains(term, autoescape=True) for name in fields]))
    for name in ('provider', 'channel_type', 'min_level', 'user'):
        value = params.get(name)
        column_name = 'user_id' if name == 'user' else name
        if value not in (None, '') and hasattr(model, column_name):
            if name == 'user':
                try:
                    value = int(value)
                except ValueError:
                    raise HTTPException(422, '账号筛选参数不合法。') from None
            statement = statement.where(getattr(model, column_name) == value)
    enabled = params.get('is_enabled')
    if enabled not in (None, '') and hasattr(model, 'is_enabled'):
        if enabled not in ('1', '0', 'true', 'false', 'True', 'False'):
            raise HTTPException(422, '启用状态筛选参数不合法。')
        statement = statement.where(model.is_enabled == (enabled in ('1', 'true', 'True')))
    return statement.order_by(model.id.desc())


# 批量读取多对多关系，避免列表页逐条查询关联对象。
async def association_ids(session, table, source_ids):
    output = defaultdict(list)
    if not source_ids:
        return output
    rows = await session.execute(select(table.c.source_id, table.c.target_id).where(table.c.source_id.in_(source_ids)).order_by(table.c.target_id))
    for source_id, target_id in rows:
        output[source_id].append(target_id)
    return output


# 为配置列表和详情批量装配关联名称，所有秘密均以掩码返回。
async def project_resources(session, kind, rows, *, include_integration_url=True):
    if not rows:
        return []
    ids = [item.id for item in rows]
    group_recipients = group_users = rule_channels = rule_recipients = rule_groups = defaultdict(list)
    if kind == 'alert-recipient-groups':
        group_recipients = await association_ids(session, ASSOCIATION_TABLES['group_recipients'], ids)
        group_users = await association_ids(session, ASSOCIATION_TABLES['group_users'], ids)
    if kind == 'alert-notification-rules':
        rule_channels = await association_ids(session, ASSOCIATION_TABLES['rule_channels'], ids)
        rule_recipients = await association_ids(session, ASSOCIATION_TABLES['rule_recipients'], ids)
        rule_groups = await association_ids(session, ASSOCIATION_TABLES['rule_groups'], ids)
    recipient_ids = {target for values in list(group_recipients.values()) + list(rule_recipients.values()) for target in values}
    user_ids = {target for values in group_users.values() for target in values}
    channel_ids = {target for values in rule_channels.values() for target in values}
    group_ids = {target for values in rule_groups.values() for target in values}
    if kind == 'alert-recipients':
        user_ids.update(item.user_id for item in rows if item.user_id)
    recipients = {item.id: item for item in await session.scalars(select(AlertRecipient).where(AlertRecipient.id.in_(recipient_ids)))} if recipient_ids else {}
    users = {item.id: item for item in await session.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    channels = {item.id: item for item in await session.scalars(select(AlertNotificationChannel).where(AlertNotificationChannel.id.in_(channel_ids)))} if channel_ids else {}
    groups = {item.id: item for item in await session.scalars(select(AlertRecipientGroup).where(AlertRecipientGroup.id.in_(group_ids)))} if group_ids else {}
    aggregation_ids = {item.aggregation_rule_id for item in rows if kind == 'alert-notification-rules' and item.aggregation_rule_id}
    escalation_ids = {item.escalation_policy_id for item in rows if kind == 'alert-notification-rules' and item.escalation_policy_id}
    aggregations = {item.id: item.name for item in await session.scalars(select(AlertAggregationRule).where(AlertAggregationRule.id.in_(aggregation_ids)))} if aggregation_ids else {}
    escalations = {item.id: item.name for item in await session.scalars(select(AlertEscalationPolicy).where(AlertEscalationPolicy.id.in_(escalation_ids)))} if escalation_ids else {}
    output = []
    for item in rows:
        value = public_columns(item)
        if kind == 'alert-integrations' and include_integration_url:
            value['webhook_url'] = f'/api/alerts/webhooks/{item.provider}/{item.token}/'
        elif kind == 'alert-recipients':
            user = users.get(item.user_id)
            value['user_detail'] = user_lite(user) if user else None
        elif kind == 'alert-recipient-groups':
            value['recipients'] = [public_columns(recipients[target]) for target in group_recipients[item.id] if target in recipients]
            value['users'] = [user_lite(users[target]) for target in group_users[item.id] if target in users]
        elif kind == 'alert-notification-channels':
            value['channel_type_display'] = {'sms': '短信', 'voice': '语音', 'email': '邮件', 'dingtalk': '钉钉', 'feishu': '飞书', 'wecom': '企业微信'}.get(item.channel_type, item.channel_type)
            value['config'] = masked_channel_config(item.config)
        elif kind == 'alert-notification-rules':
            value['channels'] = [dict(public_columns(channels[target]), config=masked_channel_config(channels[target].config), channel_type_display={'sms': '短信', 'voice': '语音', 'email': '邮件', 'dingtalk': '钉钉', 'feishu': '飞书', 'wecom': '企业微信'}.get(channels[target].channel_type, channels[target].channel_type)) for target in rule_channels[item.id] if target in channels]
            value['recipients'] = [public_columns(recipients[target]) for target in rule_recipients[item.id] if target in recipients]
            value['recipient_groups'] = [public_columns(groups[target]) for target in rule_groups[item.id] if target in groups]
            value['aggregation_rule_name'] = aggregations.get(item.aggregation_rule_id, '')
            value['escalation_policy_name'] = escalations.get(item.escalation_policy_id, '')
        output.append(value)
    return output


# 通知日志只返回业务摘要，绝不返回请求载荷、远端响应或原始错误内容。
async def filtered_notification_logs(session, params):
    statement = select(AlertNotificationLog)
    for name in ('alert', 'rule', 'channel', 'action', 'status'):
        value = params.get(name)
        if value in (None, ''):
            continue
        column = getattr(AlertNotificationLog, name + '_id' if name in {'alert', 'rule', 'channel'} else name)
        if name in {'alert', 'rule', 'channel'}:
            try:
                value = int(value)
            except ValueError:
                raise HTTPException(422, '通知日志筛选参数不合法。') from None
        statement = statement.where(column == value)
    term = (params.get('search') or '').strip()
    if term:
        statement = statement.where(AlertNotificationLog.recipient_summary.icontains(term, autoescape=True))
    return statement.order_by(AlertNotificationLog.created_at.desc(), AlertNotificationLog.id.desc())


# 批量补充渠道名和规则名，并将错误统一为不泄露远端信息的提示。
async def project_notification_logs(session, rows):
    channel_ids = {item.channel_id for item in rows if item.channel_id}
    rule_ids = {item.rule_id for item in rows if item.rule_id}
    channels = {item.id: item for item in await session.scalars(select(AlertNotificationChannel).where(AlertNotificationChannel.id.in_(channel_ids)))} if channel_ids else {}
    rules = {item.id: item.name for item in await session.scalars(select(AlertNotificationRule).where(AlertNotificationRule.id.in_(rule_ids)))} if rule_ids else {}
    output = []
    for item in rows:
        channel = channels.get(item.channel_id)
        output.append({'id': item.id, 'alert': item.alert_id, 'rule': item.rule_id, 'channel': item.channel_id, 'action': item.action, 'status': item.status, 'status_display': {'success': '成功', 'skipped': '已跳过', 'error': '失败'}.get(item.status, item.status), 'recipient_summary': item.recipient_summary, 'channel_name': channel.name if channel else '', 'channel_type': channel.channel_type if channel else '', 'rule_name': rules.get(item.rule_id, ''), 'request_payload': {}, 'response_body': '', 'sent_at': item.sent_at, 'created_at': item.created_at, 'error_message': '通知失败，请检查渠道配置。' if item.status == 'error' else ''})
    return output
