# 智能助手会话归属查询和旧序列化契约。

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiops.models import AIOpsChatMessage, AIOpsChatSession
from eventwall.services import sanitize_metadata


async def get_owned_session(session: AsyncSession, user_id: int, identifier: int, *, lock: bool = False):
    statement = select(AIOpsChatSession).where(AIOpsChatSession.id == identifier, AIOpsChatSession.user_id == user_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    item = await session.scalar(statement)
    if item is None:
        raise HTTPException(status_code=404, detail='会话不存在或已被删除，请刷新会话列表后重新选择会话，或新建会话后再提问。')
    return item


def message_response(item: AIOpsChatMessage) -> dict:
    source = item.metadata_data if isinstance(item.metadata_data, dict) else {}
    permitted = {'analysis_only', 'page_context', 'processing_status', 'processing_text', 'processing_steps', 'execution_mode', 'error_code'}
    metadata = sanitize_metadata({name: value for name, value in source.items() if name in permitted})
    return {'id': item.id, 'role': item.role, 'message_type': item.message_type, 'content': item.content, 'citations': [], 'tool_calls': [], 'metadata': metadata, 'blocks': [], 'pending_action': None, 'created_at': item.created_at}


def session_response(item: AIOpsChatSession, latest: AIOpsChatMessage | None = None) -> dict:
    return {**{name: getattr(item, name) for name in ('id', 'title', 'status', 'last_message_at', 'created_at', 'updated_at')}, 'context': sanitize_metadata(item.context), 'latest_message': {'role': latest.role, 'content': latest.content[:120], 'created_at': latest.created_at} if latest else None}


async def latest_messages(session: AsyncSession, identifiers: list[int]) -> dict:
    if not identifiers:
        return {}
    latest_id = select(AIOpsChatMessage.id).where(AIOpsChatMessage.session_id == AIOpsChatSession.id).order_by(AIOpsChatMessage.created_at.desc(), AIOpsChatMessage.id.desc()).limit(1).correlate(AIOpsChatSession).scalar_subquery()
    messages = list((await session.scalars(select(AIOpsChatMessage).join(AIOpsChatSession, AIOpsChatMessage.id == latest_id).where(AIOpsChatSession.id.in_(identifiers)))).all())
    return {item.session_id: item for item in messages}
