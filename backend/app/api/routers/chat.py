# 智能助手旧会话接口，前端调用协议保持不变。

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select

from app.api.dependencies import SessionDependency, require_permissions
from app.models import AIOpsChatMessage, AIOpsChatSession, User
from app.schemas.chat import CreateSessionInput
from app.selectors.chat import get_owned_session, latest_messages, message_response, session_response
from app.services.chat import audit_chat, create_chat_session, delete_chat_session
from app.agent_registry import action_catalog
from app.selectors.agent_config import strategy_response
from app.selectors.permissions import user_has_permissions


router = APIRouter(prefix='/api/aiops', tags=['智能助手'])
ChatUser = Annotated[User, Depends(require_permissions('aiops.chat.view'))]


@router.get('/bootstrap/', description="提供旧页面初始化载荷，读取不落库且不声明未实现工具为可执行。")
async def get_bootstrap(session: SessionDependency, actor: ChatUser):
    config = await strategy_response(session)
    permission_sets = {'chat': ('aiops.chat.view',), 'analyze': ('aiops.chat.analyze',), 'generate_task': ('aiops.task.generate',), 'execute_task': ('aiops.task.execute', 'ops.host.execute'), 'config_view': ('aiops.config.view',), 'config_manage': ('aiops.config.manage',)}
    permissions = {name: await user_has_permissions(session, actor, codes) for name, codes in permission_sets.items()}
    provider = config.get('default_provider')
    return {'enabled': config['is_enabled'] and permissions['chat'], 'welcome_message': config['welcome_message'], 'suggested_questions': config['suggested_questions'], 'action_registry': [], 'action_registry_summary': action_catalog()['summary'], 'permissions': permissions, 'provider': {'name': provider['name'] if provider else '未配置模型', 'model': provider['default_model'] if provider else ''}, 'runtime': {'allow_action_execution': False, 'require_confirmation': True, 'show_evidence': config['show_evidence'], 'allow_analysis': config['allow_analysis']}, 'active_mcp_servers': [], 'active_skills': []}


@router.get('/sessions/', description="分页查询本人会话，沿用旧时间和ID倒序以及分页响应形状。")
async def get_sessions(request: Request, session: SessionDependency, actor: ChatUser, page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1)] = 20):
    size = min(page_size, 100)
    count = await session.scalar(select(func.count()).select_from(AIOpsChatSession).where(AIOpsChatSession.user_id == actor.id))
    if page > 1 and (page - 1) * size >= count:
        raise HTTPException(status_code=404, detail='无效页码。')
    items = list((await session.scalars(select(AIOpsChatSession).where(AIOpsChatSession.user_id == actor.id).order_by(AIOpsChatSession.last_message_at.desc(), AIOpsChatSession.id.desc()).offset((page - 1) * size).limit(size))).all())
    latest = await latest_messages(session, [item.id for item in items])
    return {'count': count, 'next': str(request.url.include_query_params(page=page + 1, page_size=size)) if page * size < count else None, 'previous': str(request.url.include_query_params(page=page - 1, page_size=size)) if page > 1 else None, 'results': [session_response(item, latest.get(item.id)) for item in items]}


@router.post('/sessions/', status_code=201, description="创建当前用户会话，安全审计和业务数据原子提交。")
async def post_session(body: CreateSessionInput, request: Request, session: SessionDependency, actor: ChatUser):
    item = await create_chat_session(session, actor, body.title, body.page_context)
    await audit_chat(session, request, actor, 'create_session', item.id)
    await session.commit()
    return session_response(item)


@router.get('/sessions/{identifier}/', description="读取本人会话详情，统一隐藏他人对象存在性。")
async def get_session_detail(identifier: int, session: SessionDependency, actor: ChatUser):
    item = await get_owned_session(session, actor.id, identifier)
    latest = await latest_messages(session, [identifier])
    return session_response(item, latest.get(identifier))


@router.get('/sessions/{identifier}/messages/', description="返回本人完整历史消息数组，不改变旧前端的轮询和排序约定。")
async def get_messages(identifier: int, session: SessionDependency, actor: ChatUser):
    await get_owned_session(session, actor.id, identifier)
    items = list((await session.scalars(select(AIOpsChatMessage).where(AIOpsChatMessage.session_id == identifier).order_by(AIOpsChatMessage.created_at, AIOpsChatMessage.id))).all())
    return [message_response(item) for item in items]


@router.post('/sessions/{identifier}/delete_session/', status_code=204, description="兼容旧POST删除及DELETE入口，与删除审计在同一事务完成。")
@router.delete('/sessions/{identifier}/', status_code=204, description="兼容旧POST删除及DELETE入口，与删除审计在同一事务完成。")
async def delete_session(identifier: int, request: Request, session: SessionDependency, actor: ChatUser):
    await delete_chat_session(session, actor, identifier)
    await audit_chat(session, request, actor, 'delete_session', identifier)
    await session.commit()
    return Response(status_code=204)
