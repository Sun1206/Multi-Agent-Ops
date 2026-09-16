import asyncio
import json

import httpx
import pytest
from cryptography.fernet import Fernet

from tests_fastapi.integration.test_rbac_reads import rbac_client
from tests_fastapi.integration.test_provider_runtime import network


ROOT = '/api/aiops/admin/mcp-servers/'
VERSION = '2025-03-26'


async def create(client, headers, monkeypatch, **values):
    monkeypatch.setenv('AIOPS_CONFIG_ENCRYPTION_KEY', Fernet.generate_key().decode())
    data = {'name': 'test-http-mcp', 'server_type': 'http', 'endpoint_or_command': 'https://example.com/mcp/', 'auth_config': {'headers': {'X-Api-Key': 'test-secret'}, 'bearer_token': 'test-token', 'timeout_seconds': 5}}
    data.update(values)
    result = await client.post(ROOT, headers=headers, json=data)
    assert result.status_code == 201
    return ROOT + str(result.json()['id']) + '/'


def rpc_reply(request, result, *, sse=False):
    body = json.loads(request.content)
    payload = {'jsonrpc': '2.0', 'id': body['id'], 'result': result}
    if sse:
        return httpx.Response(200, content=('data: ' + json.dumps(payload) + '\n\n').encode(), headers={'content-type': 'text/event-stream', 'mcp-session-id': 'test-session'})
    return httpx.Response(200, json=payload, headers={'mcp-session-id': 'test-session'})


def handler(requests, tools=None, sse=False):
    def reply(request):
        requests.append(request)
        if request.method == 'DELETE':
            return httpx.Response(405)
        body = json.loads(request.content)
        if body['method'] == 'initialize':
            return rpc_reply(request, {'protocolVersion': VERSION, 'serverInfo': {'name': 'remote', 'version': '1'}, 'capabilities': {'tools': {}}}, sse=sse)
        if body['method'] == 'notifications/initialized':
            return httpx.Response(202)
        assert body['method'] == 'tools/list'
        return rpc_reply(request, {'tools': tools or []}, sse=sse)
    return reply


@pytest.mark.asyncio
@pytest.mark.parametrize('sse', [False, True])
@pytest.mark.parametrize('endpoint_path', ['/mcp/', '/mcp//', '/mcp///', '//'])
async def test_http_mcp_connection_lifecycle_contract(rbac_client, monkeypatch, sse, endpoint_path):
    client, headers, _ = rbac_client
    path = await create(client, headers, monkeypatch, endpoint_or_command='https://example.com' + endpoint_path)
    requests = []
    network(monkeypatch, handler(requests, sse=sse))
    response = await client.post(path + 'test_connection/', headers=headers)
    assert response.status_code == 200
    assert response.json()['status'] == 'success' and response.json()['protocol_version'] == VERSION
    assert response.json()['server_info']['name'] == 'remote'
    assert len(requests) == 3 and requests[-1].method == 'DELETE'
    assert all(request.url.path == endpoint_path for request in requests)
    assert requests[0].headers['X-Api-Key'] == 'test-secret'
    assert requests[1].headers['Mcp-Session-Id'] == 'test-session'
    assert 'test-secret' not in response.text and 'test-session' not in response.text


@pytest.mark.asyncio
async def test_tool_discovery_filters_legacy_whitelist_and_read_only_names(rbac_client, monkeypatch):
    client, headers, _ = rbac_client
    path = await create(client, headers, monkeypatch, tool_whitelist=['get_hosts', 'delete_hosts'])
    requests = []
    tools = [{'name': name, 'description': 'description test-secret', 'inputSchema': {'type': 'object', 'properties': {}}} for name in ['get_hosts', 'delete_hosts', 'get_other']]
    network(monkeypatch, handler(requests, tools))
    response = await client.get(path + 'list_tools/', headers=headers)
    assert response.status_code == 200
    assert response.json()['count'] == 1 and response.json()['tools'][0]['name'] == 'get_hosts'
    assert response.json()['diagnostics'][0]['tool_count'] == 1
    assert 'test-secret' not in response.text
    assert len(requests) == 4
    assert all(request.method == 'DELETE' or json.loads(request.content)['method'] != 'tools/call' for request in requests)


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['id', 'error', 'version', 'missing_info'])
async def test_invalid_rpc_or_handshake_is_not_success(rbac_client, monkeypatch, fault):
    client, headers, _ = rbac_client
    path = await create(client, headers, monkeypatch)
    def reply(request):
        if request.method == 'DELETE':
            return httpx.Response(204)
        body = json.loads(request.content)
        if fault == 'error':
            return httpx.Response(200, json={'jsonrpc': '2.0', 'id': body.get('id'), 'error': {'message': 'test-secret'}})
        result = {'protocolVersion': 'unknown' if fault == 'version' else VERSION, 'serverInfo': {'name': 'remote', 'version': '1'}, 'capabilities': {}}
        if fault == 'missing_info':
            result.pop('serverInfo')
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 'other' if fault == 'id' else body.get('id'), 'result': result})
    network(monkeypatch, reply)
    response = await client.post(path + 'test_connection/', headers=headers)
    assert response.status_code == 400 and response.json()['status'] == 'failed'
    assert 'test-secret' not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['stdio', 'platform_builtin'])
async def test_unsupported_transport_never_claims_available(rbac_client, monkeypatch, memory_session, kind):
    from aiops.models import AIOpsMCPServer
    client, headers, _ = rbac_client
    server = AIOpsMCPServer(name='unsupported', server_type=kind, endpoint_or_command='untrusted command', is_builtin=kind == 'platform_builtin')
    memory_session.add(server)
    await memory_session.commit()
    response = await client.post(ROOT + str(server.id) + '/test_connection/', headers=headers)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_mcp_runtime_authentication_permissions_and_missing_object(rbac_client, monkeypatch, memory_session):
    from rbac.models import User
    from rbac.services.accounts import issue_token
    client, headers, _ = rbac_client
    path = await create(client, headers, monkeypatch)
    user = User(username='mcp-unprivileged', password_hash='unused')
    memory_session.add(user)
    await memory_session.flush()
    token = await issue_token(memory_session, user)
    await memory_session.commit()
    for suffix, method in [('list_tools/', client.get), ('test_connection/', client.post)]:
        assert (await method(path + suffix)).status_code == 401
        assert (await method(path + suffix, headers={'Authorization': 'Token ' + token})).status_code == 403
    assert (await client.post(ROOT + '999/test_connection/', headers=headers)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['host_header', 'missing_key', 'corrupt_key', 'private'])
async def test_invalid_credentials_or_admission_never_send_request(rbac_client, monkeypatch, fault):
    client, headers, _ = rbac_client
    path = await create(client, headers, monkeypatch)
    expected = 400
    if fault == 'host_header':
        assert (await client.patch(path, headers=headers, json={'auth_config': {'headers': {'Host': 'other.example.com'}}})).status_code == 200
    elif fault == 'missing_key':
        monkeypatch.setenv('AIOPS_CONFIG_ENCRYPTION_KEY', '')
        expected = 503
    elif fault == 'corrupt_key':
        monkeypatch.setenv('AIOPS_CONFIG_ENCRYPTION_KEY', Fernet.generate_key().decode())
    else:
        assert (await client.patch(path, headers=headers, json={'endpoint_or_command': 'https://127.0.0.1/mcp'})).status_code == 200
    requests = []
    network(monkeypatch, handler(requests))
    response = await client.post(path + 'test_connection/', headers=headers)
    assert response.status_code == expected and not requests


@pytest.mark.asyncio
async def test_paginated_tool_discovery_and_write_declarations_are_never_executed(rbac_client, monkeypatch):
    client, headers, _ = rbac_client
    path = await create(client, headers, monkeypatch, auth_config={'allow_write': True})
    requests = []
    base = handler(requests)
    def reply(request):
        if request.method == 'POST' and json.loads(request.content)['method'] == 'tools/list':
            requests.append(request)
            cursor = json.loads(request.content)['params'].get('cursor')
            return rpc_reply(request, {'tools': [{'name': 'get_hosts' if cursor is None else 'delete_hosts', 'inputSchema': {'type': 'object'}}], **({'nextCursor': 'next'} if cursor is None else {})})
        return base(request)
    network(monkeypatch, reply)
    response = await client.get(path + 'list_tools/', headers=headers)
    assert response.status_code == 200 and response.json()['count'] == 2
    assert len(requests) == 5 and requests[-1].method == 'DELETE'


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['repeated_cursor', 'too_many_tools', 'gzip'])
async def test_directory_bounds_and_response_encoding_fail_safely(rbac_client, monkeypatch, fault):
    import gzip
    client, headers, _ = rbac_client
    path = await create(client, headers, monkeypatch)
    requests = []
    base = handler(requests)
    def reply(request):
        if request.method == 'POST' and json.loads(request.content)['method'] == 'tools/list':
            requests.append(request)
            if fault == 'gzip':
                return httpx.Response(200, content=gzip.compress(b'{}'), headers={'content-encoding': 'gzip'})
            result = {'tools': [{'name': 'get_hosts'}] * 201} if fault == 'too_many_tools' else {'tools': [], 'nextCursor': 'same'}
            return rpc_reply(request, result)
        return base(request)
    network(monkeypatch, reply)
    response = await client.get(path + 'list_tools/', headers=headers)
    assert response.status_code == 400 and len(requests) <= 5


@pytest.mark.asyncio
async def test_sse_response_finishes_without_waiting_for_stream_close(rbac_client, monkeypatch):
    client, headers, _ = rbac_client
    path = await create(client, headers, monkeypatch)
    requested_more, closed = asyncio.Event(), asyncio.Event()
    class Stream(httpx.AsyncByteStream):
        def __init__(self, content):
            self.content = content
        async def __aiter__(self):
            for index in range(0, len(self.content), 3):
                yield self.content[index:index + 3]
            requested_more.set()
            await asyncio.Event().wait()
        async def aclose(self):
            closed.set()
    requests = []
    base = handler(requests)
    def reply(request):
        if request.method == 'POST' and json.loads(request.content)['method'] == 'initialize':
            requests.append(request)
            payload = {'jsonrpc': '2.0', 'id': json.loads(request.content)['id'], 'result': {'protocolVersion': VERSION, 'serverInfo': {'name': '远端', 'version': '1'}, 'capabilities': {}}}
            content = ('data: ' + json.dumps(payload, ensure_ascii=False) + '\r\n\r\n').encode()
            return httpx.Response(200, stream=Stream(content), headers={'content-type': 'text/event-stream'})
        return base(request)
    network(monkeypatch, reply)
    response = await asyncio.wait_for(client.post(path + 'test_connection/', headers=headers), 2)
    assert response.status_code == 200 and response.json()['server_info']['name'] == '远端'
    assert closed.is_set() and not requested_more.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['endpoint', 'delete', 'restore'])
async def test_mcp_configuration_mutation_during_handshake_rejects_old_result(rbac_client, monkeypatch, change):
    client, headers, _ = rbac_client
    path = await create(client, headers, monkeypatch)
    entered, gate = asyncio.Event(), asyncio.Event()
    original = (await client.get(path, headers=headers)).json()['updated_at']
    requests = []
    base = handler(requests)
    async def reply(request):
        if request.method == 'POST' and json.loads(request.content)['method'] == 'initialize':
            entered.set()
            await gate.wait()
        return base(request)
    network(monkeypatch, reply)
    pending = asyncio.create_task(client.post(path + 'test_connection/', headers=headers))
    await asyncio.wait_for(entered.wait(), 2)
    if change == 'delete':
        assert (await client.delete(path, headers=headers)).status_code == 204
    else:
        for endpoint in (['https://other.example.com/mcp'] if change == 'endpoint' else ['https://other.example.com/mcp', 'https://example.com/mcp/']):
            assert (await client.patch(path, headers=headers, json={'endpoint_or_command': endpoint})).status_code == 200
        from datetime import datetime
        current = (await client.get(path, headers=headers)).json()['updated_at']
        assert (datetime.fromisoformat(current.replace('Z', '+00:00')) - datetime.fromisoformat(original.replace('Z', '+00:00'))).total_seconds() >= 1
    gate.set()
    assert (await pending).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ['list_tools/', 'test_connection/'])
@pytest.mark.parametrize('failure', ['audit', 'commit'])
async def test_mcp_audit_or_commit_failure_is_not_false_success(rbac_client, monkeypatch, endpoint, failure):
    from aiops.services import mcp_runtime
    from eventwall.models import EventRecord
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import AsyncSession
    client, headers, app = rbac_client
    path = await create(client, headers, monkeypatch)
    requests = []
    network(monkeypatch, handler(requests))
    async def fail(*args, **kwargs):
        raise RuntimeError('simulated transaction failure')
    with monkeypatch.context() as patch:
        patch.setattr(mcp_runtime if failure == 'audit' else AsyncSession, 'record_event' if failure == 'audit' else 'commit', fail)
        response = await (client.get if endpoint.startswith('list') else client.post)(path + endpoint, headers=headers)
    assert response.status_code == 500
    assert (await client.get(path, headers=headers)).status_code == 200
    async with app.state.session_factory() as database:
        count = await database.scalar(select(func.count()).select_from(EventRecord).where(EventRecord.action.in_(['list_mcp_tools', 'test_mcp_connection'])))
        assert count == 0


@pytest.mark.asyncio
async def test_authorization_header_token_echo_is_redacted(rbac_client, monkeypatch):
    client, headers, _ = rbac_client
    path = await create(client, headers, monkeypatch, auth_config={'headers': {'Authorization': 'Bearer header-secret'}})
    requests = []
    base = handler(requests)
    def reply(request):
        if request.method == 'POST' and json.loads(request.content)['method'] == 'initialize':
            requests.append(request)
            return rpc_reply(request, {'protocolVersion': VERSION, 'serverInfo': {'name': 'header-secret', 'version': '1'}, 'capabilities': {'echo': 'header-secret'}})
        return base(request)
    network(monkeypatch, reply)
    response = await client.post(path + 'test_connection/', headers=headers)
    assert response.status_code == 200 and 'header-secret' not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel', [True, False])
async def test_mcp_cancel_and_total_timeout_stop_followup_requests(rbac_client, monkeypatch, cancel):
    from aiops.models import AIOpsMCPServer
    from aiops.services.mcp_runtime import CONFIG_FIELDS, probe_http
    client, headers, app = rbac_client
    path = await create(client, headers, monkeypatch)
    async with app.state.session_factory() as database:
        item = await database.get(AIOpsMCPServer, int(path.rstrip('/').split('/')[-1]))
        config = {field: getattr(item, field) for field in CONFIG_FIELDS}
        config['id'] = item.id
    requests, entered = [], asyncio.Event()
    async def blocked(request):
        requests.append(request)
        entered.set()
        await asyncio.Event().wait()
    network(monkeypatch, blocked)
    pending = asyncio.create_task(probe_http(config, tools=True))
    await asyncio.wait_for(entered.wait(), 2)
    if cancel:
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    else:
        payload, status, count = await asyncio.wait_for(pending, 6)
        assert status == 400 and count == 1 and 'detail' in payload
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('allow_mcp', [False, True])
async def test_mcp_internal_origin_requires_dedicated_server_allowlist(rbac_client, monkeypatch, allow_mcp):
    from aiops.services import model_client
    client, headers, _ = rbac_client
    path = await create(client, headers, monkeypatch, endpoint_or_command='http://localhost:11434/mcp')
    requests = []
    network(monkeypatch, handler(requests))
    async def resolve(target):
        return ['127.0.0.1']
    monkeypatch.setattr(model_client, 'resolve_addresses', resolve)
    monkeypatch.setenv('AIOPS_MODEL_ALLOWED_INTERNAL_ORIGINS', '["http://localhost:11434"]')
    monkeypatch.setenv('AIOPS_MCP_ALLOWED_INTERNAL_ORIGINS', '["http://localhost:11434"]' if allow_mcp else '[]')
    response = await client.post(path + 'test_connection/', headers=headers)
    assert response.status_code == (200 if allow_mcp else 400)
    assert bool(requests) == allow_mcp


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['oversize', 'deep_schema', 'notification', 'session'])
async def test_mcp_rejects_unbounded_or_invalid_remote_data(rbac_client, monkeypatch, fault):
    client, headers, _ = rbac_client
    path = await create(client, headers, monkeypatch)
    requests = []
    schema = {'type': 'object'}
    for _ in range(22):
        schema = {'type': 'object', 'properties': {'nested': schema}}
    base = handler(requests, [{'name': 'get_hosts', 'inputSchema': schema}])
    def reply(request):
        if request.method == 'POST':
            method = json.loads(request.content)['method']
            if fault == 'oversize' and method == 'initialize':
                return httpx.Response(200, content=b' ' * (1024 * 1024 + 1))
            if fault == 'notification' and method == 'notifications/initialized':
                return httpx.Response(200)
        response = base(request)
        if fault == 'session' and request.method == 'POST':
            response.headers['mcp-session-id'] = 'invalid session'
        return response
    network(monkeypatch, reply)
    response = await client.get(path + 'list_tools/', headers=headers)
    assert response.status_code == 400
    assert 'test-secret' not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['nonfinite', 'media_type'])
async def test_mcp_rejects_non_json_payload_or_wrong_response_media_type(rbac_client, monkeypatch, fault):
    client, headers, _ = rbac_client
    path = await create(client, headers, monkeypatch)
    base = handler([])
    def reply(request):
        response = base(request)
        if request.method == 'POST' and json.loads(request.content)['method'] == 'initialize':
            payload = json.loads(response.content)
            payload['result']['capabilities']['extra'] = float('nan') if fault == 'nonfinite' else 'value'
            return httpx.Response(200, content=json.dumps(payload).encode(), headers={'content-type': 'application/json' if fault == 'nonfinite' else 'text/html'})
        return response
    network(monkeypatch, reply)
    response = await client.post(path + 'test_connection/', headers=headers)
    assert response.status_code == 400 and response.json()['status'] == 'failed'


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['disabled', 'permissions'])
async def test_mcp_actor_changed_during_network_cannot_publish_result(rbac_client, monkeypatch, change):
    from sqlalchemy import delete, select
    from rbac.models import User
    from rbac.models.authorization import user_roles
    client, headers, app = rbac_client
    path = await create(client, headers, monkeypatch)
    entered, gate = asyncio.Event(), asyncio.Event()
    base = handler([])
    async def reply(request):
        if request.method == 'POST' and json.loads(request.content)['method'] == 'initialize':
            entered.set()
            await gate.wait()
        return base(request)
    network(monkeypatch, reply)
    pending = asyncio.create_task(client.post(path + 'test_connection/', headers=headers))
    await asyncio.wait_for(entered.wait(), 2)
    async with app.state.session_factory() as database:
        user = await database.scalar(select(User).where(User.username == 'admin'))
        if change == 'disabled':
            user.is_active = False
        else:
            user.is_superuser = False
            await database.execute(delete(user_roles).where(user_roles.c.user_id == user.id))
        await database.commit()
    gate.set()
    assert (await pending).status_code == 403
