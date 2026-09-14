import asyncio
import json
import os

from cryptography.fernet import InvalidToken
from dotenv import dotenv_values
from fastapi import HTTPException
from sqlalchemy import update

from app.models import AIOpsModelProvider, User
from app.services import model_client
from app.services.agent_config import lock_strategies
from app.services.config_secrets import config_cipher
from app.services.events import record_event
from app.services.provider_probe import discover_models, probe_payload, resolved_model, safe_model_id
from app.selectors.agent_config import get_resource
from app.selectors.permissions import user_has_permissions


CONNECTION_FIELDS = ('provider_type', 'base_url', 'default_model', 'backup_model', 'api_key_encrypted', 'is_enabled', 'timeout_seconds', 'temperature', 'max_tokens', 'updated_at')
SUCCESS_MESSAGE = '模型连接测试成功。'
FAILURE_MESSAGE = '模型连接测试失败，请检查模型与服务配置。'


# 快照只保留影响连接的实际字段，不包含诊断状态；凭据只在内部比较。
def snapshot(provider):
    return {field: getattr(provider, field) for field in CONNECTION_FIELDS}


# 读取已保存提供商并解密内部请求凭据；离开数据库会话后才允许网络等待。
# 缺失服务端密钥沿用503，密文不可解密或提供商不完整返回安全400。
async def read_snapshot(factory, identifier):
    async with factory() as database:
        provider = await get_resource(database, 'providers', identifier)
        state = snapshot(provider)
    if not state['is_enabled'] or state['provider_type'] != 'openai_compatible' or not state['base_url']:
        raise HTTPException(status_code=400, detail='提供商未启用或连接配置不完整。')
    try:
        key = config_cipher().decrypt(state['api_key_encrypted'].encode()).decode()
    except (InvalidToken, UnicodeError, ValueError):
        raise HTTPException(status_code=400, detail='模型凭据无法解密，请检查配置。') from None
    if not key or any(ord(char) < 32 or ord(char) == 127 for char in key):
        raise HTTPException(status_code=400, detail='模型凭据未配置或格式不合法。')
    return state, key


# 仅读取服务端origin准入配置，验证完整DNS答案并返回固定连接地址。
# 准入失败不执行目录回退、不发送API Key，也不修改提供商诊断状态。
async def admitted_target(state):
    raw = os.environ.get('AIOPS_MODEL_ALLOWED_INTERNAL_ORIGINS')
    if raw is None:
        raw = dotenv_values('.env').get('AIOPS_MODEL_ALLOWED_INTERNAL_ORIGINS') or '[]'
    try:
        allowed = json.loads(raw)
        if not isinstance(allowed, list) or any(not isinstance(value, str) for value in allowed):
            raise ValueError()
        target = model_client.validate_origin(state['base_url'], allowed)
        addresses = await model_client.resolve_addresses(target)
        # Every DNS answer is checked before any directory fallback or credential-bearing request.
        addresses = model_client.validate_addresses(addresses, target.internal_allowed)
        return target, addresses
    except (ValueError, OSError):
        raise HTTPException(status_code=400, detail='模型地址未通过服务端准入检查。') from None


# 网络等待使用已结束读取事务的快照，整个目录/探测链共用一个截止时间。
async def run_diagnostic(state, key, *, connection, probe):
    budget = min(float(state['timeout_seconds']), 90.0)
    deadline = asyncio.get_running_loop().time() + budget
    count = 0
    target = addresses = None
    async def call(method, suffix, payload):
        nonlocal count
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise model_client.ModelRequestError('模型请求超时。')
        count += 1
        return await model_client.request_json(target, key, method, suffix, payload, remaining, pinned_addresses=addresses)
    try:
        async with asyncio.timeout(budget):
            target, addresses = await admitted_target(state)
            if connection:
                if not safe_model_id(state['default_model'], key):
                    raise HTTPException(status_code=400, detail='请配置合法的默认模型。')
                try:
                    result = await call('POST', '/chat/completions', probe_payload(state['default_model']))
                    model_client.text_content(result)
                    return {'status': 'success', 'message': SUCCESS_MESSAGE, 'resolved_model': resolved_model(result, state['default_model'], key)}, 200, count
                except model_client.ModelAdmissionError:
                    raise HTTPException(status_code=400, detail='模型地址未通过服务端准入检查。') from None
                except model_client.ModelRequestError:
                    return {'status': 'failed', 'message': FAILURE_MESSAGE}, 400, count
            return await discover_models(call, state, key, probe), 200, count
    except TimeoutError:
        if target is None:
            raise HTTPException(status_code=400, detail='模型地址解析超时。') from None
        if connection:
            return {'status': 'failed', 'message': FAILURE_MESSAGE}, 400, count
        return {'detail': '模型目录或能力探测超时，请稍后重试。'}, 400, count
    except model_client.ModelAdmissionError:
        raise HTTPException(status_code=400, detail='模型地址未通过服务端准入检查。') from None
    except model_client.ModelRequestError:
        return {'detail': '模型目录或能力探测失败，请检查配置。'}, 400, count


# 按既有策略→提供商锁顺序复核配置；状态与审计同事务，失败不会假报成功。
async def save_diagnostic(factory, identifier, actor_id, state, result, request, *, connection, probe, count):
    async with factory() as database:
        await lock_strategies(database)
        provider = await database.get(AIOpsModelProvider, identifier, with_for_update=True, populate_existing=True)
        if provider is None or snapshot(provider) != state:
            raise HTTPException(status_code=409, detail='提供商配置已变化或被删除，请重新测试。')
        actor = await database.get(User, actor_id)
        if actor is None or not actor.is_active or not await user_has_permissions(database, actor, ('aiops.config.manage',)):
            raise HTTPException(status_code=403, detail='账号或配置管理权限已变化。')
        if connection:
            # updated_at在此作为配置变更标记，显式保留，避免诊断完成使另一并发诊断失效。
            await database.execute(update(AIOpsModelProvider).where(AIOpsModelProvider.id == identifier).values(last_test_status=result['status'], last_test_message=result['message'], updated_at=provider.updated_at))
        outcome = result['status'] if connection else ('failed' if 'detail' in result else ('verified' if result['recommendation'] else 'catalog'))
        await record_event(database, actor=actor, method=request.method, path=request.url.path, ip_address=request.client.host if request.client else '', correlation_id=getattr(request.state, 'correlation_id', ''), action='test_model_provider' if connection else 'list_provider_models', title='模型提供商诊断', resource_type='aiops_model_provider', resource_id=str(identifier), metadata={'probe': probe if not connection else False, 'request_count': count, 'result': outcome}, module='aiops', category='configuration')
        await database.commit()


# 为两个旧接口编排读取、受限网络诊断和最终复核；不复用请求事务等待模型。
# 返回载荷和HTTP状态供薄路由使用，状态及审计提交失败直接传播安全服务器错误。
async def diagnose_provider(identifier, request, session, actor, *, connection=False, probe=True):
    actor_id = actor.id
    # 先释放依赖中的认证读取事务，防止远端等待占用该事务或数据库锁。
    await session.rollback()
    factory = request.app.state.session_factory
    state, key = await read_snapshot(factory, identifier)
    result, status, count = await run_diagnostic(state, key, connection=connection, probe=probe)
    await save_diagnostic(factory, identifier, actor_id, state, result, request, connection=connection, probe=probe, count=count)
    return result, status
