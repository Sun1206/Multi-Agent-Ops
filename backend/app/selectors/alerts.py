from collections import Counter, defaultdict

from fastapi import HTTPException
from sqlalchemy import func, inspect, or_, select

from app.models import Alert, AlertAction, AlertClaim, AlertIntegration, AlertNotificationChannel, AlertNotificationLog, AlertNotificationRule, Host
from app.services.events import is_sensitive_key, sanitize_metadata


DEFAULT_GROUP_BY = ['source_type', 'environment', 'service', 'cluster', 'namespace', 'resource']
ACTION_LABELS = {'acknowledge': '确认', 'claim': '认领', 'unclaim': '取消认领', 'mute': '屏蔽', 'resolve': '恢复', 'close': '关闭', 'reopen': '重新打开', 'notify': '通知', 'escalate': '升级', 'webhook': '接收', 'comment': '备注'}
STATUS_LABELS = {'active': '活跃', 'resolved': '已恢复', 'muted': '已屏蔽', 'closed': '已关闭'}
SOURCE_LABELS = {'prometheus': 'Prometheus', 'zabbix': 'Zabbix', 'nightingale': '夜莺', 'aliyun': '阿里云', 'generic': '通用'}
BUSINESS_FIELDS = {'source_type', 'source', 'service', 'environment', 'cluster', 'namespace', 'region', 'business_line', 'resource_type', 'resource', 'level', 'status', 'metric_name', 'title'}


# 查询参数中的布尔标记只接受旧页面使用的明确值，拒绝将任意字符串当成真。
def boolean(raw):
    if raw in ('1', 'true', 'True'):
        return True
    if raw in ('0', 'false', 'False'):
        return False
    raise HTTPException(422, '布尔筛选参数不合法。')


# 默认分页20，最大200；无效页码明确拒绝，查询参数仍保留在上一页/下一页链接中。
def pagination(params):
    try:
        page, size = int(params.get('page', 1)), int(params.get('page_size', 20))
        if page < 1 or not 1 <= size <= 200:
            raise ValueError()
        return page, size
    except (TypeError, ValueError):
        raise HTTPException(422, '分页参数不合法。') from None


# 所有事件查询共享筛选规则；认领依据实际记录，不依据确认标记或辅助claimed_by字段。
async def filtered_alerts(session, params):
    statement = select(Alert)
    enums = {'level': {'critical', 'warning', 'info'}, 'status': set(STATUS_LABELS), 'source_type': set(SOURCE_LABELS)}
    for name in (BUSINESS_FIELDS - {'resource'}) | {'claimed_by'}:
        raw = params.get(name)
        if raw:
            if name in enums and raw not in enums[name]:
                raise HTTPException(422, '告警筛选枚举不合法。')
            statement = statement.where(getattr(Alert, name) == raw)
    for name in ('is_acknowledged', 'is_suppressed'):
        if params.get(name) not in (None, ''):
            statement = statement.where(getattr(Alert, name) == boolean(params[name]))
    claims = select(AlertClaim.id).where(AlertClaim.alert_id == Alert.id).exists()
    claimed = params.get('claimed', params.get('ack'))
    if claimed not in (None, ''):
        statement = statement.where(claims if boolean(claimed) else ~claims)
    if params.get('only_open') not in (None, '') and boolean(params['only_open']):
        statement = statement.where(Alert.status.notin_(['resolved', 'closed']))
    # resource搜索是包含匹配；此前通用维度不应额外施加精确匹配。
    if params.get('resource'):
        term = params['resource']
        statement = statement.where(or_(Alert.resource.icontains(term, autoescape=True), Alert.host_id.in_(select(Host.id).where(Host.hostname.icontains(term, autoescape=True)))))
    term = (params.get('system_name') or params.get('system') or '').strip()
    if term:
        statement = statement.where(or_(Alert.business_line == term, Alert.host_id.in_(select(Host.id).where(Host.business_line == term))))
    if params.get('search'):
        term = params['search']
        statement = statement.where(or_(*[getattr(Alert, name).icontains(term, autoescape=True) for name in ('title', 'source', 'message', 'service', 'resource', 'business_line', 'cluster', 'namespace')], Alert.host_id.in_(select(Host.id).where(Host.hostname.icontains(term, autoescape=True)))))
    statement = statement.order_by(Alert.last_received_at.desc(), Alert.created_at.desc(), Alert.id.desc())
    if params.get('label_key') and params.get('label_value'):
        rows = (await session.scalars(statement.limit(5000))).all()
        ids = [row.id for row in rows if isinstance(row.labels, dict) and str(row.labels.get(params['label_key'], '')) == params['label_value']]
        statement = statement.where(Alert.id.in_(ids))
    return statement


# 通用实体字段复制为旧serializer名称；嵌套JSON过滤敏感键，不暴露内部列命名。
def public_columns(item):
    result = {column.key: getattr(item, column.key) for column in inspect(type(item)).column_attrs}
    for name in list(result):
        value = result[name]
        if isinstance(value, (dict, list)):
            result[name] = sanitize_metadata(value)
        if name.endswith('_id') and name != 'external_id':
            result[name[:-3]] = result.pop(name)
    if 'metadata_data' in result:
        result['metadata'] = result.pop('metadata_data')
    return result


# 操作记录输出旧展示字段；metadata仅作脱敏业务信息，不执行其中内容。
def action_response(item):
    result = public_columns(item)
    result['action_display'] = ACTION_LABELS.get(item.action, item.action)
    return result


# 批量装配分页/详情所有关联，认领与动作不逐条查询；通知仅显示已有安全摘要。
async def project_alerts(session, rows, actor, *, current=False):
    ids = [row.id for row in rows]
    if not ids:
        return []
    claims, actions, notifications = defaultdict(list), defaultdict(list), defaultdict(list)
    claim_query = select(AlertClaim).where(AlertClaim.alert_id.in_(ids)).order_by(AlertClaim.claimed_at, AlertClaim.id)
    action_query = select(AlertAction).where(AlertAction.alert_id.in_(ids)).order_by(AlertAction.created_at.desc(), AlertAction.id.desc())
    # 写流程已先锁父告警，关联结果也用当前读；GET保持普通只读查询，不申请写锁。
    if current:
        claim_query, action_query = claim_query.with_for_update(), action_query.with_for_update()
    for item in await session.scalars(claim_query):
        claims[item.alert_id].append({'id': item.id, 'claimant': item.claimant, 'claimed_at': item.claimed_at})
    for item in await session.scalars(action_query):
        actions[item.alert_id].append(action_response(item))
    # 窗口函数限制每条告警最多5条，避免从属通知历史无界读取。
    ranked = select(AlertNotificationLog.id, func.row_number().over(partition_by=AlertNotificationLog.alert_id, order_by=(AlertNotificationLog.created_at.desc(), AlertNotificationLog.id.desc())).label('rank')).where(AlertNotificationLog.alert_id.in_(ids)).subquery()
    logs = list((await session.scalars(select(AlertNotificationLog).join(ranked, ranked.c.id == AlertNotificationLog.id).where(ranked.c.rank <= 5).order_by(AlertNotificationLog.created_at.desc(), AlertNotificationLog.id.desc()))).all())
    channels = {item.id: item for item in await session.scalars(select(AlertNotificationChannel).where(AlertNotificationChannel.id.in_([log.channel_id for log in logs if log.channel_id])))}
    rules = {item.id: item.name for item in await session.scalars(select(AlertNotificationRule).where(AlertNotificationRule.id.in_([log.rule_id for log in logs if log.rule_id])))}
    for log in logs:
        channel = channels.get(log.channel_id)
        notifications[log.alert_id].append({'id': log.id, 'alert': log.alert_id, 'channel': log.channel_id, 'rule': log.rule_id, 'action': log.action, 'status': log.status, 'status_display': {'success': '成功', 'skipped': '已跳过', 'error': '失败'}.get(log.status, log.status), 'recipient_summary': log.recipient_summary, 'created_at': log.created_at, 'sent_at': log.sent_at, 'channel_name': channel.name if channel else '', 'channel_type': channel.channel_type if channel else '', 'rule_name': rules.get(log.rule_id, ''), 'request_payload': {}, 'response_body': '', 'error_message': '通知失败，请检查渠道配置。' if log.status == 'error' else ''})
    hosts = {item.id: item.hostname for item in await session.scalars(select(Host).where(Host.id.in_([row.host_id for row in rows if row.host_id])))}
    integrations = {item.id: item.name for item in await session.scalars(select(AlertIntegration).where(AlertIntegration.id.in_([row.integration_id for row in rows if row.integration_id])))}
    result = []
    for row in rows:
        value = public_columns(row)
        claimants = claims[row.id]
        value.update(level_display=dict(Alert.LEVEL_CHOICES).get(row.level, row.level), status_display=STATUS_LABELS.get(row.status, row.status), source_type_display=SOURCE_LABELS.get(row.source_type, row.source_type), host_name=hosts.get(row.host_id, ''), integration_name=integrations.get(row.integration_id, ''), claimants=claimants, claimant_count=len(claimants), claimed_by='、'.join(item['claimant'] for item in claimants), claimed_at=claimants[0]['claimed_at'] if claimants else None, current_user_claimed=any(item['claimant'] == actor.username for item in claimants), actions=actions[row.id], recent_notifications=notifications[row.id])
        result.append(value)
    return result


# 只定位当前目标；写流程请求行锁，不借助前端提交的对象状态。
async def get_alert(session, identifier, *, lock=False):
    statement = select(Alert).where(Alert.id == identifier).execution_options(populate_existing=True)
    if lock:
        statement = statement.with_for_update()
    item = await session.scalar(statement)
    if item is None:
        raise HTTPException(404, '告警不存在。')
    return item


# 统计沿用旧最多5000条语义，不使用分页结果，也不把确认当作认领。
async def summarize(session, statement):
    rows = list((await session.scalars(statement.limit(5000))).all())
    claimed = set((await session.scalars(select(AlertClaim.alert_id).where(AlertClaim.alert_id.in_([row.id for row in rows])))).all())
    levels, statuses = Counter(row.level for row in rows), Counter(row.status for row in rows)
    return {'total': len(rows), **{key: levels[key] for key in ('critical', 'warning', 'info')}, **{key: statuses[key] for key in STATUS_LABELS}, 'claimed': len(claimed), 'unacknowledged': len(rows) - len(claimed), 'suppressed': sum(row.is_suppressed or row.status == 'muted' for row in rows)}


# 分组维度只允许公开字段和labels/annotations；最新时间继续使用旧created_at规则。
async def group_alerts(session, statement, raw):
    dimensions = [part.strip() for part in raw.split(',') if part.strip()] if raw else DEFAULT_GROUP_BY
    if not dimensions or len(dimensions) > 12 or any(is_sensitive_key(key) or len(key) > 128 or (key not in BUSINESS_FIELDS and not ((key.startswith('label.') or key.startswith('annotation.')) and key.split('.', 1)[1])) for key in dimensions):
        raise HTTPException(422, '告警分组维度不合法。')
    rows = list((await session.scalars(statement.order_by(None).order_by(Alert.created_at.desc(), Alert.id.desc()).limit(5000))).all())
    claimed = set((await session.scalars(select(AlertClaim.alert_id).where(AlertClaim.alert_id.in_([row.id for row in rows])))).all())
    groups = {}
    for row in rows:
        values = {}
        for key in dimensions:
            if '.' in key:
                prefix, name = key.split('.', 1)
                data = row.labels if prefix == 'label' else row.annotations
                value = data.get(name, '') if isinstance(data, dict) else ''
            else:
                value = getattr(row, key)
            # 先递归脱敏再转展示字符串，防止非敏感父标签内嵌token/password绕过检查。
            value = sanitize_metadata(value)
            values[key] = str(value) if value not in (None, '') else '-'
        key = ' | '.join(f'{name}={value}' for name, value in values.items())
        item = groups.setdefault(key, {'key': key, 'dimensions': values, 'total': 0, 'critical': 0, 'warning': 0, 'info': 0, 'unacknowledged': 0, 'suppressed': 0, 'latest_at': row.created_at, 'sample_alert_id': row.id, 'sample_title': row.title})
        item['total'] += 1
        item[row.level] += 1
        item['unacknowledged'] += row.id not in claimed
        item['suppressed'] += row.is_suppressed or row.status == 'muted'
    return sorted(groups.values(), key=lambda item: (item['critical'], item['warning'], item['total']), reverse=True)
