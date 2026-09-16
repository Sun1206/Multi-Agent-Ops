# 智能助手旧会话接口，前端调用协议保持不变。

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select

from aidevops.dependencies import SessionDependency, require_permissions
from aiops.models import AIOpsChatMessage, AIOpsChatSession
from rbac.models import User
from aiops.schemas.chat import ChatInput, CreateSessionInput, normalize_page_context
from aiops.services.chat_jobs import WORKER_TAG, now, update_result
from aiops.selectors.chat import get_owned_session, latest_messages, message_response, session_response
from aiops.services.chat import audit_chat, create_chat_session, delete_chat_session
from aiops.agent_registry import action_catalog
from aiops.selectors.agent_config import strategy_response
from rbac.selectors.permissions import user_has_permissions


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
    jobs = request.app.state.chat_jobs
    async with jobs.submission(identifier):
        await delete_chat_session(session, actor, identifier)
        await audit_chat(session, request, actor, 'delete_session', identifier)
        await session.commit()
        await jobs.cancel_session(identifier)
    return Response(status_code=204)


async def prepare_submission(identifier, body, request, session, actor):
    chat = await get_owned_session(session, actor.id, identifier, lock=True)
    if actor.username == 'demo':
        raise HTTPException(status_code=403, detail='演示账号不能发起对话。')
    jobs = request.app.state.chat_jobs
    jobs.reserve()
    started = False
    try:
        context = normalize_page_context(body.page_context)
        if context:
            chat.context = {**(chat.context if isinstance(chat.context, dict) else {}), 'page_context': context}
        user_message = AIOpsChatMessage(session_id=identifier, role='user', content=body.content, metadata_data={'analysis_only': body.analysis_only, 'page_context': context})
        assistant_message = AIOpsChatMessage(session_id=identifier, role='assistant', content='正在生成回复，请稍等。', metadata_data={'processing_status': 'pending', 'processing_text': '请求已提交，正在排队处理', 'analysis_only': body.analysis_only, 'page_context': context, 'processing_steps': [{'title': '排队中', 'status': 'pending', 'timestamp': now().isoformat()}], 'tool_events': [], 'worker_tag': WORKER_TAG})
        session.add_all([user_message, assistant_message])
        chat.last_message_at = now()
        if chat.title == '新会话':
            chat.title = body.content[:48] or '新会话'
        await session.flush()
        await audit_chat(session, request, actor, 'send_message', identifier)
        commit_task = asyncio.create_task(session.commit())
        try:
            await asyncio.shield(commit_task)
        except asyncio.CancelledError:
            # Finish the commit before releasing the request session; a committed placeholder needs a terminal state.
            try:
                await commit_task
                await update_result(request.app.state.session_factory, identifier, assistant_message.id, actor.id, 'failed', '提交请求已中断，请重新提交。')
            finally:
                raise
        response = {'user_message': message_response(user_message), 'assistant_message': message_response(assistant_message), 'pending_action': None}
        try:
            task = jobs.start(identifier, user_message.id, assistant_message.id, actor.id)
        except Exception:
            await update_result(request.app.state.session_factory, identifier, assistant_message.id, actor.id, 'failed', '对话调度失败，请重新提交。')
            raise HTTPException(status_code=503, detail='对话调度暂不可用，请稍后重试。') from None
        started = True
        return response, task
    finally:
        if not started:
            jobs.release()


async def submit_message(identifier, body, request, session, actor, synchronous):
    async with request.app.state.chat_jobs.submission(identifier):
        response, task = await prepare_submission(identifier, body, request, session, actor)
    if synchronous:
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if not task.cancelled():
                raise
            await get_owned_session(session, actor.id, identifier)
            raise HTTPException(status_code=503, detail='对话请求已中断，请重新提交。') from None
        message = await session.get(AIOpsChatMessage, response['assistant_message']['id'], populate_existing=True)
        if message is None:
            raise HTTPException(status_code=404, detail='会话已被删除。')
        response['assistant_message'] = message_response(message)
    return response


@router.post('/sessions/{identifier}/send_message_async/', status_code=201, description='提交对话请求，由后台处理并通过历史消息接口轮询结果。')
async def send_message_async(identifier: int, body: ChatInput, request: Request, session: SessionDependency, actor: ChatUser):
    return await submit_message(identifier, body, request, session, actor, False)


@router.post('/sessions/{identifier}/send_message/', status_code=201, description='兼容同步对话入口，等待模型处理完成后返回消息。')
async def send_message(identifier: int, body: ChatInput, request: Request, session: SessionDependency, actor: ChatUser):
    return await submit_message(identifier, body, request, session, actor, True)
