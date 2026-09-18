import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import perf_counter

from cryptography.fernet import InvalidToken
from fastapi import HTTPException
from dotenv import dotenv_values
from sqlalchemy import select

from aiops.models import AIOpsAgentConfig, AIOpsChatMessage, AIOpsChatSession, AIOpsModelProvider
from aiops.services.model_invocations import model_invocation
from rbac.models import User
from aiops.schemas.chat import normalize_page_context
from aidevops import restricted_http as model_client
from aidevops.config_secrets import config_cipher
from eventwall.services import record_event
from aiops.selectors.chat import get_owned_session
from rbac.selectors.permissions import user_has_permissions


logger = logging.getLogger(__name__)
WORKER_TAG = 'ordinary_chat_v1'
PROVIDER_FIELDS = ('id', 'name', 'base_url', 'default_model', 'api_key_encrypted', 'provider_type', 'is_enabled', 'timeout_seconds', 'temperature', 'max_tokens', 'price_currency', 'input_token_price_per_1m', 'output_token_price_per_1m')
CONFIG_FIELDS = ('default_provider_id', 'system_prompt', 'is_enabled', 'max_history_messages')


def now():
    return datetime.now(timezone.utc)


def snapshot(config, provider):
    return ({name: getattr(config, name) for name in CONFIG_FIELDS}, {name: getattr(provider, name) for name in PROVIDER_FIELDS})


async def prepare_request(factory, session_id, user_message_id, user_id):
    async with factory() as database:
        chat = await get_owned_session(database, user_id, session_id)
        actor = await database.get(User, user_id)
        if actor is None or not actor.is_active or not await user_has_permissions(database, actor, ('aiops.chat.view',)):
            raise model_client.ModelRequestError('账号已停用。')
        config = await database.scalar(select(AIOpsAgentConfig).where(AIOpsAgentConfig.name == 'default'))
        provider = await database.get(AIOpsModelProvider, config.default_provider_id) if config and config.default_provider_id else None
        if not config or not config.is_enabled or not provider or not provider.is_enabled or not provider.base_url or not provider.default_model:
            raise model_client.ModelRequestError('尚未配置或启用可用的默认模型。')
        try:
            key = config_cipher().decrypt(provider.api_key_encrypted.encode()).decode()
        except (HTTPException, InvalidToken, UnicodeError, ValueError):
            raise model_client.ModelRequestError('模型凭据无法解密，请检查服务端配置。') from None
        config_state, provider_state = snapshot(config, provider)
        current = await database.get(AIOpsChatMessage, user_message_id)
        if current is None or current.session_id != chat.id:
            raise model_client.ModelRequestError('消息已被删除。')
        history = list((await database.scalars(select(AIOpsChatMessage).where(AIOpsChatMessage.session_id == chat.id, AIOpsChatMessage.id < current.id, AIOpsChatMessage.role.in_(['user', 'assistant']), AIOpsChatMessage.message_type == 'text').order_by(AIOpsChatMessage.id.desc()).limit(100))).all())
        selected = []
        for message in history:
            metadata = message.metadata_data if isinstance(message.metadata_data, dict) else {}
            if message.role == 'assistant' and metadata.get('processing_status', 'completed') != 'completed':
                continue
            selected.append({'role': message.role, 'content': message.content})
        selected = selected[:config.max_history_messages]
        prompt = config.system_prompt + '\n当前只支持普通文本对话，没有平台资源查询、工具或任务执行能力，不得声称已查询或执行。'
        if len(prompt) > 30000:
            raise model_client.ModelRequestError('系统提示词过长，请调整配置。')
        selected.reverse()
        while selected and len(prompt) + sum(len(message['content']) for message in selected) > 30000:
            selected.pop(0)
        payload = {'model': provider.default_model, 'temperature': provider.temperature, 'max_tokens': provider.max_tokens, 'messages': [{'role': 'system', 'content': prompt}] + selected + [{'role': 'user', 'content': current.content}]}
    raw = os.environ.get('AIOPS_MODEL_ALLOWED_INTERNAL_ORIGINS')
    if raw is None:
        raw = dotenv_values('.env').get('AIOPS_MODEL_ALLOWED_INTERNAL_ORIGINS') or '[]'
    allowed = json.loads(raw)
    if not isinstance(allowed, list) or any(not isinstance(item, str) for item in allowed):
        raise model_client.ModelRequestError('服务端模型地址准入配置不合法。')
    target = model_client.validate_origin(provider_state['base_url'], allowed)
    return config_state, provider_state, target, key, payload, actor.username


async def update_result(factory, session_id, assistant_id, user_id, status, content, expected=None, invocation_values=None):
    async with factory() as database:
        config = await database.scalar(select(AIOpsAgentConfig).where(AIOpsAgentConfig.name == 'default').with_for_update().execution_options(populate_existing=True))
        provider = await database.get(AIOpsModelProvider, config.default_provider_id, with_for_update=True) if config and config.default_provider_id else None
        chat = await database.scalar(select(AIOpsChatSession).where(AIOpsChatSession.id == session_id, AIOpsChatSession.user_id == user_id).with_for_update())
        message = await database.get(AIOpsChatMessage, assistant_id)
        actor = await database.get(User, user_id)
        if chat is None or message is None or message.session_id != session_id or actor is None:
            return
        if not actor.is_active or not await user_has_permissions(database, actor, ('aiops.chat.view',)) or (expected is not None and (not config or not provider or snapshot(config, provider) != expected)):
            status, content = 'failed', '账号或模型配置已变化，请重新提交问题。'
        metadata = dict(message.metadata_data or {})
        metadata.update(processing_status=status, processing_text={'running': '正在生成回复', 'completed': '回复已完成', 'failed': '回复失败'}[status], processing_steps=[{'title': {'running': '模型请求', 'completed': '回复完成', 'failed': '处理失败'}[status], 'status': status, 'timestamp': now().isoformat()}])
        message.metadata_data = metadata
        message.content = content
        message.message_type = 'error' if status == 'failed' else 'text'
        if status in ('completed', 'failed'):
            chat.last_message_at = now()
            if invocation_values is not None:
                database.add(model_invocation(**invocation_values))
            await record_event(database, actor=actor, method='POST', path=f'/api/aiops/sessions/{session_id}/send_message_async/', ip_address='', correlation_id=f'aiops-chat-message:{assistant_id}', action='complete_chat' if status == 'completed' else 'fail_chat', title='智能助手对话处理', resource_type='aiops_chat_session', resource_id=str(session_id), metadata={'message_id': assistant_id, 'result': status}, module='aiops', category='chat')
        await database.commit()


class ChatJobs:
    def __init__(self, application, max_pending=32):
        self.application = application
        self.max_pending = max_pending
        self.pending = 0
        self.tasks = set()
        self.tails = {}
        self.closed = False
        self.submissions = {}
        self.session_tasks = {}

    @asynccontextmanager
    async def submission(self, session_id):
        lock, count = self.submissions.get(session_id, (asyncio.Lock(), 0))
        self.submissions[session_id] = (lock, count + 1)
        try:
            async with lock:
                yield
        finally:
            _, count = self.submissions[session_id]
            if count == 1:
                self.submissions.pop(session_id)
            else:
                self.submissions[session_id] = (lock, count - 1)

    def reserve(self):
        if self.closed or self.pending >= self.max_pending:
            raise HTTPException(status_code=429, detail='当前对话请求较多，请稍后重试。')
        self.pending += 1

    def release(self):
        self.pending -= 1

    def start(self, session_id, user_message_id, assistant_id, user_id):
        previous = self.tails.get(session_id)
        task = asyncio.create_task(self.run(previous, session_id, user_message_id, assistant_id, user_id))
        self.tasks.add(task)
        self.tails[session_id] = task
        self.session_tasks.setdefault(session_id, set()).add(task)
        def finished(completed):
            self.tasks.discard(completed)
            self.release()
            if self.tails.get(session_id) is completed:
                self.tails.pop(session_id, None)
            tasks = self.session_tasks.get(session_id, set())
            tasks.discard(completed)
            if not tasks:
                self.session_tasks.pop(session_id, None)
        task.add_done_callback(finished)
        return task

    async def run(self, previous, session_id, user_message_id, assistant_id, user_id):
        factory = self.application.state.session_factory
        config = provider = result = invocation = None
        started = None
        try:
            if previous:
                await asyncio.shield(previous)
            await update_result(factory, session_id, assistant_id, user_id, 'running', '正在生成回复，请稍等。')
            config, provider, target, key, payload, username = await prepare_request(factory, session_id, user_message_id, user_id)
            request_summary = {
                'message_count': len(payload['messages']),
                'content_length': sum(len(message.get('content', '')) for message in payload['messages']),
            }
            started = perf_counter()
            result = await model_client.request_completion(target, key, payload, provider['timeout_seconds'])
            latency_ms = round((perf_counter() - started) * 1000)
            content = model_client.text_content(result).replace(key, '***')
            invocation = {
                'provider': provider, 'session_id': session_id, 'message_id': assistant_id,
                'username': username, 'latency_ms': latency_ms, 'result': result,
                'status': 'success', 'termination': 'completed', 'request_summary': request_summary,
            }
            await update_result(factory, session_id, assistant_id, user_id, 'completed', content, (config, provider), invocation)
        except asyncio.CancelledError:
            if started is not None and invocation is None:
                invocation = {
                    'provider': provider, 'session_id': session_id, 'message_id': assistant_id,
                    'username': username, 'latency_ms': round((perf_counter() - started) * 1000),
                    'result': result, 'status': 'failed', 'termination': 'cancelled',
                    'request_summary': request_summary,
                }
            await update_result(factory, session_id, assistant_id, user_id, 'failed', '对话请求已中断，请重新提交。', (config, provider) if config and provider else None, invocation)
            raise
        except Exception:
            try:
                if started is not None and invocation is None:
                    invocation = {
                        'provider': provider, 'session_id': session_id, 'message_id': assistant_id,
                        'username': username, 'latency_ms': round((perf_counter() - started) * 1000),
                        'result': result, 'status': 'failed', 'termination': 'failure',
                        'request_summary': request_summary,
                    }
                await update_result(factory, session_id, assistant_id, user_id, 'failed', '模型不可用或请求失败，请检查默认模型与服务端配置后重试。', (config, provider) if config and provider else None, invocation)
            except Exception:
                logger.error('对话终态保存失败 message_id=%s', assistant_id)

    async def wait_all(self):
        if self.tasks:
            await asyncio.gather(*tuple(self.tasks), return_exceptions=True)

    async def close(self):
        self.closed = True
        for task in tuple(self.tasks):
            task.cancel()
        await self.wait_all()
        if hasattr(self.application.state, 'session_factory'):
            await recover_interrupted(self.application.state.session_factory)

    async def cancel_session(self, session_id):
        tasks = tuple(self.session_tasks.get(session_id, ()))
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def recover_interrupted(factory):
    async with factory() as database:
        messages = list((await database.scalars(select(AIOpsChatMessage).where(AIOpsChatMessage.role == 'assistant', AIOpsChatMessage.metadata_data['worker_tag'].as_string() == WORKER_TAG, AIOpsChatMessage.metadata_data['processing_status'].as_string().in_(['pending', 'running'])))).all())
        for message in messages:
            metadata = message.metadata_data if isinstance(message.metadata_data, dict) else {}
            if metadata.get('worker_tag') == WORKER_TAG and metadata.get('processing_status') in ('pending', 'running'):
                message.metadata_data = {**metadata, 'processing_status': 'failed', 'processing_text': '服务重启中断了此请求，请重新提交。'}
                message.content = '服务重启中断了此请求，请重新提交。'
                message.message_type = 'error'
        await database.commit()
