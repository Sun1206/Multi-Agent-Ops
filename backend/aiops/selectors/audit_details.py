# 将真实调用记录投影为现有运行概览页面需要的分页数据，不返回对话正文或原始载荷。

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from aiops.models import AIOpsChatMessage, AIOpsChatSession, AIOpsModelInvocation, AIOpsModelProvider, AIOpsPendingAction, AIOpsToolInvocation
from rbac.models import User


MODELS = {'sessions': AIOpsChatSession, 'tool-invocations': AIOpsToolInvocation, 'model-invocations': AIOpsModelInvocation, 'actions': AIOpsPendingAction}
TRACE_FIELDS = {'skill-traces': 'skill_traces', 'action-traces': 'action_traces'}
STATUS_LABELS = {'success': '成功', 'failed': '失败', 'pending': '待处理', 'confirmed': '已确认', 'executed': '已执行', 'canceled': '已取消'}
PURPOSE_LABELS = {'chat_planning': '聊天规划', 'answer_formatting': '回答整形', 'parameter_extraction': '参数抽取', 'model_probe': '模型探测', 'connection_test': '连接测试'}
RISK_LABELS = {'low': '低', 'medium': '中', 'high': '高', 'critical': '极高', 'read_only': '只读', 'draft': '草稿', 'write': '写入', 'execute': '执行'}


# 原始请求、响应和错误可能含凭据；仅输出服务端已知的统计计数及有限状态字段。
def safe_summary(value):
    if not isinstance(value, dict):
        return {}
    counters = {'message_count', 'content_length', 'prompt_length', 'input_length', 'round', 'tool_count', 'count', 'result_count', 'total', 'span_count'}
    output = {key: item for key, item in value.items() if key in counters and type(item) is int and item >= 0}
    for key, allowed in {
        'result': {'success', 'failed'},
        'termination': {'completed', 'tool_calls', 'failure', 'cancelled'},
        'error_code': {'cancelled', 'worker_restarted', 'authorization_changed', 'timeout', 'execution_failed', 'tool_failed'},
    }.items():
        if isinstance(value.get(key), str) and value[key] in allowed:
            output[key] = value[key]
    if type(value.get('has_usage')) is bool:
        output['has_usage'] = value['has_usage']
    return output


# 只读取命中记录的固定展示字段，避免把可扩展元数据整体暴露给审计页。
def trace_projection(trace, kind):
    if not isinstance(trace, dict) or not isinstance(trace.get('key'), str) or not trace['key'].strip() or not isinstance(trace.get('label'), str) or not trace['label'].strip():
        return None
    output = {'key': trace['key'][:128], 'label': trace['label'][:128], 'inferred': False}
    for name in ('status', 'category', 'risk_level', 'hit_reason', 'action_code', 'action_display_name', 'route'):
        if isinstance(trace.get(name), str):
            output[name] = trace[name][:256]
    for name in ('used_tools', 'applicable_actions', 'applicable_action_names', 'skills', 'skill_names', 'allowed_tools'):
        values = trace.get(name)
        output[name] = [value[:128] for value in values[:100] if isinstance(value, str)] if isinstance(values, list) else []
    output['draft_generated'] = trace.get('draft_generated') is True
    if kind == 'skill-traces':
        output.update(slug=output['key'], name=output['label'])
    else:
        output.update(code=output['key'], display_name=output['label'])
    output['risk_level_display'] = RISK_LABELS.get(output.get('risk_level'), '')
    return output


# 会话和调用明细共用筛选；采用参数绑定和字面包含，避免通配符扩大查询范围。
def filtered_statement(kind, filters):
    model = AIOpsChatMessage if kind in TRACE_FIELDS else MODELS[kind]
    if kind == 'sessions':
        statement = select(model, User.username).join(User, User.id == model.user_id)
        query_columns = [model.title, User.username]
    else:
        statement = select(model, AIOpsChatSession.title, User.username).outerjoin(AIOpsChatSession, AIOpsChatSession.id == model.session_id).outerjoin(User, User.id == AIOpsChatSession.user_id)
        query_columns = [AIOpsChatSession.title, User.username]
        if kind == 'tool-invocations':
            query_columns.append(model.tool_name)
        elif kind == 'actions':
            query_columns += [model.title, model.action_type]
        elif kind == 'model-invocations':
            statement = statement.add_columns(AIOpsModelProvider.name).outerjoin(AIOpsModelProvider, AIOpsModelProvider.id == model.provider_id)
            query_columns += [model.requested_model, model.resolved_model, model.username, AIOpsModelProvider.name]
    if kind in TRACE_FIELDS:
        statement = statement.where(model.role == 'assistant')
    elif filters.q.strip():
        statement = statement.where(or_(*(column.contains(filters.q.strip(), autoescape=True) for column in query_columns)))
    if filters.username.strip():
        column = model.username if kind == 'model-invocations' else User.username
        statement = statement.where(column.contains(filters.username.strip(), autoescape=True))
    if filters.status and kind not in TRACE_FIELDS:
        statement = statement.where(model.status == filters.status)
    if filters.risk_level and kind == 'actions':
        statement = statement.where(model.risk_level == filters.risk_level)
    if filters.purpose and kind == 'model-invocations':
        statement = statement.where(model.purpose == filters.purpose)
    if filters.start is not None:
        statement = statement.where(model.created_at >= filters.start, model.created_at <= filters.end)
    return statement.order_by(model.created_at.desc(), model.id.desc())


# 构造兼容页面的分页链接，越界页返回明确错误，空结果第一页正常返回。
def page_result(request, filters, count, rows):
    if filters.page > 1 and (filters.page - 1) * filters.page_size >= count:
        raise HTTPException(404, '无效页面。')
    url = request.url.include_query_params(page_size=filters.page_size)
    return {'count': count, 'next': str(url.include_query_params(page=filters.page + 1)) if filters.page * filters.page_size < count else None, 'previous': str(url.include_query_params(page=filters.page - 1)) if filters.page > 1 else None, 'results': rows}


# 按消息分块展开真实命中记录，以消息编号和原数组位置作为稳定标识。
# 删除时保留空槽，因此其他记录的标识不会随数组缩短而改变。
async def trace_page(session, request, kind, filters):
    statement = filtered_statement(kind, filters)
    offset, count, rows = 0, 0, []
    while True:
        batch = (await session.execute(statement.offset(offset).limit(200))).all()
        if not batch:
            break
        for message, title, username in batch:
            metadata = message.metadata_data if isinstance(message.metadata_data, dict) else {}
            traces = metadata.get(TRACE_FIELDS[kind], [])
            for index, trace in enumerate(traces if isinstance(traces, list) else []):
                item = trace_projection(trace, kind)
                if item is None:
                    continue
                if filters.status and item.get('status') != filters.status:
                    continue
                if filters.risk_level and item.get('risk_level') != filters.risk_level:
                    continue
                text = ' '.join([item['key'], item['label'], title or '', username or ''])
                if filters.q.strip().casefold() not in text.casefold():
                    continue
                count += 1
                if (filters.page - 1) * filters.page_size < count <= filters.page * filters.page_size:
                    rows.append({**item, 'id': f'{message.id}:{index}', 'message_id': message.id, 'session_id': message.session_id, 'session_title': title or '', 'username': username or '', 'created_at': message.created_at})
        offset += len(batch)
    return page_result(request, filters, count, rows)


# 批量汇总当前页会话的消息数、工具数和命中信息，避免逐行查询。
async def session_extras(session, identifiers):
    extras = {identifier: {'message_count': 0, 'tool_invocation_count': 0, 'skill_trace': {'items': []}, 'action_trace': {}} for identifier in identifiers}
    if not identifiers:
        return extras
    counts = await session.execute(select(AIOpsToolInvocation.session_id, func.count()).where(AIOpsToolInvocation.session_id.in_(identifiers)).group_by(AIOpsToolInvocation.session_id))
    for identifier, count in counts:
        extras[identifier]['tool_invocation_count'] = count
    statement = select(AIOpsChatMessage).where(AIOpsChatMessage.session_id.in_(identifiers)).order_by(AIOpsChatMessage.created_at.desc(), AIOpsChatMessage.id.desc())
    stream = await session.stream_scalars(statement.execution_options(yield_per=200))
    async for message in stream:
        extra = extras[message.session_id]
        extra['message_count'] += 1
        metadata = message.metadata_data if isinstance(message.metadata_data, dict) else {}
        if message.role != 'assistant':
            continue
        for kind, field in TRACE_FIELDS.items():
            values = metadata.get(field, [])
            items = [item for value in values if (item := trace_projection(value, kind))] if isinstance(values, list) else []
            if kind == 'skill-traces' and not extra['skill_trace']['items']:
                extra['skill_trace']['items'] = items[:100]
            elif kind == 'action-traces' and not extra['action_trace'] and items:
                extra['action_trace'] = items[0]
    for extra in extras.values():
        items = extra['skill_trace']['items']
        extra['skill_trace'].update(matched_count=len(items), enabled_count=len(items))
    return extras


# 从有限字段构造各类调用记录；删除提供商或会话后仍保留独立模型调用统计。
async def list_details(session, request, kind, filters):
    if kind in TRACE_FIELDS:
        return await trace_page(session, request, kind, filters)
    statement = filtered_statement(kind, filters)
    count = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    records = (await session.execute(statement.offset((filters.page - 1) * filters.page_size).limit(filters.page_size))).all()
    extras = await session_extras(session, [row[0].id for row in records]) if kind == 'sessions' else {}
    rows = []
    for record in records:
        item = record[0]
        row = {'id': item.id, 'status': item.status, 'status_display': STATUS_LABELS.get(item.status, item.status), 'created_at': item.created_at}
        if kind == 'sessions':
            row.update(title=item.title, username=record[1], last_message_at=item.last_message_at, updated_at=item.updated_at, **extras[item.id])
        else:
            row.update(session_id=item.session_id, message_id=item.message_id, session_title=record[1] or '', username=record[2] or '')
            if kind == 'tool-invocations':
                row.update(tool_name=item.tool_name, latency_ms=item.latency_ms, request_payload=safe_summary(item.request_payload), response_summary=safe_summary(item.response_summary))
            elif kind == 'model-invocations':
                for field in ('purpose', 'requested_model', 'resolved_model', 'latency_ms', 'prompt_tokens', 'completion_tokens', 'total_tokens', 'estimated_cost_usd', 'estimated_cost_currency', 'username'):
                    row[field] = getattr(item, field)
                row.update(provider_name=record[3] or '已删除提供商', purpose_display=PURPOSE_LABELS.get(item.purpose, item.purpose), request_summary=safe_summary(item.request_summary), response_summary=safe_summary(item.response_summary))
            else:
                row.update(title=item.title, action_type=item.action_type, risk_level=item.risk_level, risk_level_display=RISK_LABELS.get(item.risk_level, item.risk_level), confirmed_by=item.confirmed_by, confirmed_at=item.confirmed_at, updated_at=item.updated_at, action_payload={}, result_payload={})
                result = item.result_payload if isinstance(item.result_payload, dict) else {}
                row['result_payload'] = {key: value for key, value in result.items() if key in {'task_id', 'created_task_id', 'host_task_id'} and type(value) is int and value > 0}
        rows.append(row)
    return page_result(request, filters, count, rows)
