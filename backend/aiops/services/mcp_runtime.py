import asyncio
import json
import math
import os
import re
from dataclasses import replace
from urllib.parse import urlsplit, urlunsplit

import httpx
from cryptography.fernet import InvalidToken
from dotenv import dotenv_values
from fastapi import HTTPException

from aiops.models import AIOpsMCPServer
from rbac.models import User
from aiops.selectors.agent_config import get_resource
from rbac.selectors.permissions import user_has_permissions
from aidevops import restricted_http as model_client
from aiops.services.agent_config import lock_strategies
from aidevops.config_secrets import ENVELOPE, config_cipher
from eventwall.services import record_event
from aiops.services.mcp_http import HttpMcpSession
from aiops.services.mcp_tools import McpError, project_tools, public_data


CONFIG_FIELDS = ('name', 'server_type', 'endpoint_or_command', 'auth_config', 'tool_whitelist', 'is_enabled', 'updated_at')
PROTECTED_HEADERS = {'host', 'content-length', 'transfer-encoding', 'connection', 'accept', 'accept-encoding', 'content-type', 'origin', 'proxy-authorization', 'proxy-connection', 'upgrade', 'trailer', 'te'}


# 只解密HTTP连接真正使用的凭据，env或其他配置不会进入进程环境和请求。
def secret_value(value):
    if isinstance(value, dict) and set(value) == {ENVELOPE}:
        try:
            return config_cipher().decrypt(value[ENVELOPE].encode()).decode()
        except (InvalidToken, ValueError, UnicodeError, AttributeError):
            raise HTTPException(status_code=400, detail='MCP鉴权凭据无法解密。') from None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail='MCP鉴权字段必须是字符串。')
    return value


# 验证并解密HTTP鉴权参数，收集脱敏原文；拒绝控制头、非法字符及超时/写入开关类型。
def auth_parameters(config):
    auth = config['auth_config']
    if not isinstance(auth, dict) or not isinstance(auth.get('headers', {}), dict):
        raise HTTPException(status_code=400, detail='MCP鉴权配置格式不合法。')
    headers, secrets = {}, []
    for name, value in auth.get('headers', {}).items():
        lower = name.lower()
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) or lower in PROTECTED_HEADERS or lower.startswith('mcp-') or lower in headers:
            raise HTTPException(status_code=400, detail='MCP鉴权不能覆盖网络或协议控制头。')
        raw = secret_value(value)
        if len(raw) > 8192 or any(ord(char) < 32 or ord(char) >= 127 for char in raw):
            raise HTTPException(status_code=400, detail='MCP鉴权请求头格式不合法。')
        headers[lower] = raw
        if raw:
            secrets.append(raw)
            # 远端可能只回显鉴权方案后的凭据，不能仅脱敏整个Authorization头。
            if lower == 'authorization':
                parts = raw.split(None, 1)
                if len(parts) == 2:
                    secrets.append(parts[1])
    if auth.get('bearer_token'):
        token = secret_value(auth['bearer_token'])
        if not token or len(token) > 8192 or any(ord(char) < 33 or ord(char) >= 127 for char in token):
            raise HTTPException(status_code=400, detail='MCP Bearer Token格式不合法。')
        headers.setdefault('authorization', 'Bearer ' + token)
        secrets.append(token)
    try:
        raw_timeout = auth.get('timeout_seconds', 20)
        timeout = float(raw_timeout)
        if isinstance(raw_timeout, bool) or not math.isfinite(timeout) or not 5 <= timeout <= 120:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail='MCP超时配置必须为5–120秒。') from None
    allow_write = auth.get('allow_write', False)
    if not isinstance(allow_write, bool):
        raise HTTPException(status_code=400, detail='MCP allow_write必须为布尔值。')
    return headers, secrets, min(timeout, 90), allow_write


# 公网HTTPS默认允许；HTTP/内网等只能通过独立的服务端MCP origin列表授权。
async def admitted_target(config):
    raw = os.environ.get('AIOPS_MCP_ALLOWED_INTERNAL_ORIGINS')
    if raw is None:
        raw = dotenv_values('.env').get('AIOPS_MCP_ALLOWED_INTERNAL_ORIGINS') or '[]'
    try:
        allowed = json.loads(raw)
        if not isinstance(allowed, list) or any(not isinstance(item, str) for item in allowed):
            raise ValueError()
        endpoint = config['endpoint_or_command']
        target = model_client.validate_origin(endpoint, allowed)
        # 复用主机准入但恢复原始完整路径，模型base_url的去尾斜线规则不适用于MCP。
        canonical = urlsplit(target.url)
        target = replace(target, url=urlunsplit((canonical.scheme, canonical.netloc, urlsplit(endpoint).path, '', '')))
        addresses = model_client.validate_addresses(await model_client.resolve_addresses(target), target.internal_allowed)
        return target, addresses
    except (ValueError, OSError):
        raise HTTPException(status_code=400, detail='MCP地址未通过服务端准入检查。') from None


# 整条握手/通知/分页共用截止时间，取消不再发后续RPC或远端清理请求。
async def probe_http(config, *, tools):
    headers, secrets, timeout, allow_write = auth_parameters(config)
    deadline = asyncio.get_running_loop().time() + timeout
    session, cancelled = None, False
    try:
        async with asyncio.timeout(timeout):
            target, addresses = await admitted_target(config)
            transport = httpx.AsyncHTTPTransport(verify=True, trust_env=False, retries=0)
            if not hasattr(transport, '_pool') or not hasattr(transport._pool, '_network_backend'):
                await transport.aclose()
                raise McpError('MCP网络客户端版本不兼容。')
            transport._pool._network_backend = model_client.PinnedBackend(target.host, target.port, addresses[0])
            async with httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False) as client:
                session = HttpMcpSession(client, target, headers, deadline)
                try:
                    result = await session.initialize()
                    private = secrets + ([session.session_id] if session.session_id else [])
                    if tools:
                        rows = await session.list_tools() if 'tools' in result['capabilities'] else []
                        projected = project_tools(rows, config['tool_whitelist'], allow_write, private)
                        payload = {'tools': projected, 'count': len(projected), 'diagnostics': [{'server_id': config['id'], 'name': config['name'], 'status': 'connected', 'tool_count': len(projected), 'message': '仅完成HTTP连接及工具声明发现，未执行工具。'}]}
                    else:
                        payload = {'status': 'success', 'message': 'MCP HTTP连接成功，未执行工具。', 'server_info': public_data({field: result['serverInfo'][field] for field in ('name', 'version')}, private), 'protocol_version': result['protocolVersion'], 'capabilities': public_data(result['capabilities'], private)}
                except asyncio.CancelledError:
                    cancelled = True
                    raise
                finally:
                    if not cancelled:
                        await session.close()
            return payload, 200, session.request_count
    except asyncio.CancelledError:
        raise
    except (TimeoutError, McpError, httpx.HTTPError, OSError, ValueError, UnicodeError, RecursionError):
        message = 'MCP HTTP连接或工具发现失败，请检查服务、协议和鉴权配置。'
        return ({'detail': message} if tools else {'status': 'failed', 'message': message}), 400, session.request_count if session else 0


# 不持有读取事务等待网络；完成后锁定并复核配置及账号，审计与事务原子提交。
async def diagnose_mcp(identifier, request, session, actor, *, tools=False):
    actor_id = actor.id
    await session.rollback()
    factory = request.app.state.session_factory
    async with factory() as database:
        item = await get_resource(database, 'mcp-servers', identifier)
        config = {field: getattr(item, field) for field in CONFIG_FIELDS}
        config['id'] = identifier
    if not config['is_enabled'] or not config['endpoint_or_command']:
        raise HTTPException(status_code=400, detail='MCP未启用或连接地址未配置。')
    if config['server_type'] != 'http':
        raise HTTPException(status_code=400, detail='当前仅支持HTTP MCP诊断，STDIO及平台内置执行尚未接入。')
    payload, status, count = await probe_http(config, tools=tools)
    async with factory() as database:
        await lock_strategies(database)
        current = await database.get(AIOpsMCPServer, identifier, with_for_update=True, populate_existing=True)
        if current is None or any(getattr(current, field) != config[field] for field in CONFIG_FIELDS):
            raise HTTPException(status_code=409, detail='MCP配置已变化或被删除，请重新测试。')
        user = await database.get(User, actor_id)
        if user is None or not user.is_active or not await user_has_permissions(database, user, ('aiops.config.manage',)):
            raise HTTPException(status_code=403, detail='账号或MCP管理权限已变化。')
        await record_event(database, actor=user, method=request.method, path=request.url.path, ip_address=request.client.host if request.client else '', correlation_id=getattr(request.state, 'correlation_id', ''), action='list_mcp_tools' if tools else 'test_mcp_connection', title='HTTP MCP连接诊断', resource_type='aiops_mcp_server', resource_id=str(identifier), metadata={'result': 'success' if status == 200 else 'failed', 'request_count': count, 'tool_count': payload.get('count', 0)}, module='aiops', category='configuration')
        await database.commit()
    return payload, status
