# 会话变更与安全审计；不调用外部模型或工具。

from fastapi import Request
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from aiops.models import AIOpsChatSession
from rbac.models import User
from aiops.schemas.chat import normalize_page_context
from aiops.selectors.chat import get_owned_session
from eventwall.services import record_event


async def audit_chat(session: AsyncSession, request: Request, actor: User, action: str, identifier: int):
    await record_event(session, actor=actor, method=request.method, path=request.url.path, ip_address=request.client.host if request.client else '', correlation_id=getattr(request.state, 'correlation_id', ''), action=action, title='智能助手会话变更', resource_type='aiops_chat_session', resource_id=str(identifier), metadata={}, module='aiops', category='chat')


async def create_chat_session(session: AsyncSession, actor: User, title: str, page_context):
    context = normalize_page_context(page_context)
    item = AIOpsChatSession(user_id=actor.id, title=title or '新会话', context={'page_context': context} if context else {})
    session.add(item)
    await session.flush()
    return item


async def delete_chat_session(session: AsyncSession, actor: User, identifier: int):
    await get_owned_session(session, actor.id, identifier, lock=True)
    await session.execute(delete(AIOpsChatSession).where(AIOpsChatSession.id == identifier, AIOpsChatSession.user_id == actor.id).execution_options(synchronize_session=False))
