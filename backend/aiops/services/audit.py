# 审计清理采用先校验全部目标再修改的单事务流程，禁止清理仍在执行的记录。

import re
from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import delete, select

from aiops.models import AIOpsChatMessage, AIOpsChatSession, AIOpsToolInvocation, AIOpsPendingAction
from aiops.selectors.audit_details import MODELS, TRACE_FIELDS, trace_projection
from eventwall.services import record_event


# 验证由服务端生成的命中标识，只允许正消息编号和非负数组位置。
def parse_trace_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,18}:[0-9]{1,9}', value):
        raise HTTPException(422, '命中记录编号格式无效。')
    return tuple(int(part) for part in value.split(':'))


# 锁定受影响会话并检查持久化运行状态，与聊天提交的会话行锁保持一致。
# 状态查询使用当前读，避免MySQL可重复读事务读取加锁前的旧运行状态。
async def ensure_idle(session, session_ids):
    if not session_ids:
        return
    await session.execute(select(AIOpsChatSession.id).where(AIOpsChatSession.id.in_(session_ids)).order_by(AIOpsChatSession.id).with_for_update())
    pending = await session.scalar(select(AIOpsChatMessage.id).where(
        AIOpsChatMessage.session_id.in_(session_ids),
        AIOpsChatMessage.metadata_data['processing_status'].as_string().in_(['pending', 'running']),
    ).limit(1).with_for_update())
    tool = await session.scalar(select(AIOpsToolInvocation.id).where(AIOpsToolInvocation.session_id.in_(session_ids), AIOpsToolInvocation.status == 'pending').limit(1).with_for_update())
    action = await session.scalar(select(AIOpsPendingAction.id).where(AIOpsPendingAction.session_id.in_(session_ids), AIOpsPendingAction.status == 'confirmed').limit(1).with_for_update())
    if pending is not None or tool is not None or action is not None:
        raise HTTPException(409, '相关会话或动作仍在运行，请结束后再清理。')


# 只清理指定类型和编号；缺失任一目标则整体返回404，调用者负责原子提交。
async def delete_details(session, request, actor, kind, identifiers):
    identifiers = list(dict.fromkeys(identifiers))
    model = AIOpsChatMessage if kind in TRACE_FIELDS else MODELS[kind]
    targets = [parse_trace_id(value) for value in identifiers] if kind in TRACE_FIELDS else []
    ids = sorted({pair[0] for pair in targets}) if targets else sorted(identifiers)
    initial = list((await session.scalars(select(model).where(model.id.in_(ids)))).all())
    if len(initial) != len(ids):
        raise HTTPException(404, '部分审计记录不存在，请刷新列表。')
    session_ids = [item.id if kind == 'sessions' else item.session_id for item in initial]
    await ensure_idle(session, sorted({identifier for identifier in session_ids if identifier is not None}))
    rows = list((await session.scalars(select(model).where(model.id.in_(ids)).order_by(model.id).with_for_update().execution_options(populate_existing=True))).all())
    if len(rows) != len(ids):
        raise HTTPException(404, '部分审计记录不存在，请刷新列表。')
    if targets:
        updates = {item.id: deepcopy(item.metadata_data) if isinstance(item.metadata_data, dict) else {} for item in rows}
        by_id = {item.id: item for item in rows}
        field = TRACE_FIELDS[kind]
        for message_id, index in targets:
            values = updates[message_id].get(field)
            if by_id[message_id].role != 'assistant' or not isinstance(values, list) or index >= len(values) or trace_projection(values[index], kind) is None:
                raise HTTPException(404, '部分命中记录不存在，请刷新列表。')
            values[index] = None
        for item in rows:
            item.metadata_data = updates[item.id]
    else:
        await session.execute(delete(model).where(model.id.in_(ids)).execution_options(synchronize_session=False))
    await record_event(
        session, actor=actor, method=request.method, path=request.url.path,
        ip_address=request.client.host if request.client else '',
        correlation_id=getattr(request.state, 'correlation_id', ''),
        action='delete_aiops_audit', title='清理智能助手审计记录',
        resource_type='aiops_audit', resource_id=kind,
        metadata={'kind': kind, 'deleted_count': len(identifiers), 'identifiers': identifiers},
        module='aiops', category='audit',
    )
    return {'deleted': len(identifiers)}
