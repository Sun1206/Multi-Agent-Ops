import asyncio
import json

import httpx
import pytest
from cryptography.fernet import Fernet

from tests_fastapi.integration.test_rbac_reads import rbac_client


ROOT = '/api/aiops/admin/providers/'


async def provider(client, headers, monkeypatch):
    monkeypatch.setenv('AIOPS_CONFIG_ENCRYPTION_KEY', Fernet.generate_key().decode())
    result = await client.post(ROOT, headers=headers, json={'name': 'runtime-model', 'base_url': 'https://example.com/v1', 'default_model': 'default', 'backup_model': 'backup', 'api_key': 'test-secret'})
    assert result.status_code == 201
    return ROOT + str(result.json()['id']) + '/'


def network(monkeypatch, handler):
    from types import SimpleNamespace
    from aiops.services import model_client
    async def addresses(target):
        return ['8.8.8.8']
    monkeypatch.setattr(model_client, 'resolve_addresses', addresses)
    def transport(**kwargs):
        result = httpx.MockTransport(handler)
        result._pool = SimpleNamespace(_network_backend=None)
        return result
    monkeypatch.setattr(httpx, 'AsyncHTTPTransport', transport)


@pytest.mark.asyncio
async def test_connection_contract_and_safe_persisted_status(rbac_client, monkeypatch):
    client, headers, app = rbac_client
    path = await provider(client, headers, monkeypatch)
    requests = []
    def reply(request):
        requests.append(request)
        return httpx.Response(200, json={'model': 'default', 'choices': [{'message': {'content': 'arbitrary remote answer test-secret'}}]})
    network(monkeypatch, reply)
    result = await client.post(path + 'test_connection/', headers=headers)
    assert result.status_code == 200
    assert result.json()['status'] == 'success' and result.json()['resolved_model'] == 'default'
    assert 'test-secret' not in result.text and 'arbitrary remote' not in result.text
    data = json.loads(requests[0].content)
    assert data['max_tokens'] == 32 and data['temperature'] == 0 and data['stream'] is False
    assert len(requests) == 1
    assert (await client.get(path, headers=headers)).json()['last_test_status'] == 'success'


@pytest.mark.asyncio
async def test_catalog_without_probe_does_not_generate_or_change_provider(rbac_client, monkeypatch):
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    requests = []
    def reply(request):
        requests.append(request)
        return httpx.Response(200, json={'data': [{'id': 'one'}, {'id': 'one'}, {'id': 'bad\n'}, {'id': 'echo-test-secret'}, {'id': 'x' * 129}, {'id': 'two'}]})
    network(monkeypatch, reply)
    result = await client.get(path + 'models/?probe=false', headers=headers)
    assert result.status_code == 200
    assert result.json()['models'] == [{'id': 'one'}, {'id': 'two'}]
    assert result.json()['count'] == 2 and result.json()['recommendation'] is None
    assert requests[0].method == 'GET' and requests[0].url.path == '/v1/models' and len(requests) == 1
    assert (await client.get(path, headers=headers)).json()['last_test_status'] == 'unknown'


@pytest.mark.asyncio
@pytest.mark.parametrize('reply_mode', ['text_only', 'bad_tool_arguments', 'all_failed', 'different_resolved_model'])
async def test_probe_never_overclaims_tool_support_or_success(rbac_client, monkeypatch, reply_mode):
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    requests = []
    def reply(request):
        requests.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': 'default'}, {'id': 'backup'}]})
        data = json.loads(request.content)
        if reply_mode == 'all_failed':
            return httpx.Response(200, json={'choices': [{'message': {'content': ''}}]})
        if 'tools' not in data or reply_mode == 'text_only':
            return httpx.Response(200, json={'model': 'real-model', 'choices': [{'message': {'content': 'answer'}}]})
        name = data['tools'][0]['function']['name']
        args = '{"ok":1}' if reply_mode == 'bad_tool_arguments' else '{"ok":true}'
        return httpx.Response(200, json={'model': 'other-model', 'choices': [{'message': {'tool_calls': [{'id': 'call', 'type': 'function', 'function': {'name': name, 'arguments': args}}]}}]})
    network(monkeypatch, reply)
    response = await client.get(path + 'models/', headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert len(requests) <= 5
    if reply_mode == 'all_failed':
        assert result['recommendation'] is None and result['probe_error']
    else:
        assert result['recommendation']['verified']
        assert not result['recommendation']['supports_tool_calling']


@pytest.mark.asyncio
async def test_directory_model_count_is_bounded(rbac_client, monkeypatch):
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    network(monkeypatch, lambda request: httpx.Response(200, json={'data': [{'id': f'model-{index}'} for index in range(250)]}))
    response = await client.get(path + 'models/?probe=false', headers=headers)
    assert response.status_code == 200 and response.json()['count'] == 200


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ['models/?probe=false', 'test_connection/'])
@pytest.mark.parametrize('failure', ['audit', 'commit'])
async def test_audit_or_commit_failure_rolls_back_all_diagnostic_changes(rbac_client, monkeypatch, endpoint, failure):
    from aiops.services import provider_runtime
    from sqlalchemy.ext.asyncio import AsyncSession
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    network(monkeypatch, lambda request: httpx.Response(200, json={'data': [{'id': 'default'}], 'choices': [{'message': {'content': 'answer'}}]}))
    async def fail(*args, **kwargs):
        raise RuntimeError('simulated persistence failure')
    with monkeypatch.context() as patch:
        patch.setattr(provider_runtime if failure == 'audit' else AsyncSession, 'record_event' if failure == 'audit' else 'commit', fail)
        method = client.post if endpoint.startswith('test') else client.get
        response = await method(path + endpoint, headers=headers)
    assert response.status_code == 500
    assert (await client.get(path, headers=headers)).json()['last_test_status'] == 'unknown'


@pytest.mark.asyncio
async def test_mixed_dns_answers_fail_before_catalog_or_probe_and_without_fallback(rbac_client, monkeypatch):
    from aiops.services import model_client
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    calls = []
    network(monkeypatch, lambda request: calls.append(request) or httpx.Response(200, json={}))
    async def addresses(target):
        return ['8.8.8.8', '127.0.0.1']
    monkeypatch.setattr(model_client, 'resolve_addresses', addresses)
    response = await client.get(path + 'models/', headers=headers)
    assert response.status_code == 400 and not calls
    assert (await client.get(path, headers=headers)).json()['last_test_status'] == 'unknown'


@pytest.mark.asyncio
async def test_cancelled_probe_never_starts_followup_request(rbac_client, monkeypatch):
    from aiops.services.provider_runtime import read_snapshot, run_diagnostic
    client, headers, app = rbac_client
    path = await provider(client, headers, monkeypatch)
    identifier = int(path.rstrip('/').split('/')[-1])
    state, key = await read_snapshot(app.state.session_factory, identifier)
    entered = asyncio.Event()
    calls = []
    async def reply(request):
        calls.append(request)
        entered.set()
        await asyncio.Event().wait()
    network(monkeypatch, reply)
    pending = asyncio.create_task(run_diagnostic(state, key, connection=False, probe=True))
    await asyncio.wait_for(entered.wait(), 2)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_catalog_and_all_probes_share_total_timeout(rbac_client, monkeypatch):
    from aiops.services.provider_runtime import read_snapshot, run_diagnostic
    client, headers, app = rbac_client
    path = await provider(client, headers, monkeypatch)
    identifier = int(path.rstrip('/').split('/')[-1])
    state, key = await read_snapshot(app.state.session_factory, identifier)
    state['timeout_seconds'] = .03
    calls = []
    async def reply(request):
        calls.append(request)
        if request.method == 'GET':
            await asyncio.sleep(.01)
            return httpx.Response(200, json={'data': [{'id': 'default'}]})
        await asyncio.Event().wait()
    network(monkeypatch, reply)
    result, status, count = await run_diagnostic(state, key, connection=False, probe=True)
    assert status == 400 and 'detail' in result and len(calls) == count == 2


@pytest.mark.asyncio
async def test_disabled_actor_during_probe_does_not_save_success(rbac_client, monkeypatch, memory_session):
    from aiops.models import AIOpsModelProvider
    from rbac.models import User
    from sqlalchemy import select, update
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    entered, gate = asyncio.Event(), asyncio.Event()
    async def reply(request):
        entered.set()
        await gate.wait()
        return httpx.Response(200, json={'choices': [{'message': {'content': 'answer'}}]})
    network(monkeypatch, reply)
    pending = asyncio.create_task(client.post(path + 'test_connection/', headers=headers))
    await asyncio.wait_for(entered.wait(), 2)
    await memory_session.execute(update(User).where(User.username == 'admin').values(is_active=False))
    await memory_session.commit()
    gate.set()
    assert (await pending).status_code == 403
    memory_session.expire_all()
    provider_row = await memory_session.scalar(select(AIOpsModelProvider))
    assert provider_row.last_test_status == 'unknown'


@pytest.mark.asyncio
async def test_deep_untrusted_json_is_safe_failure_not_internal_error(rbac_client, monkeypatch):
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    network(monkeypatch, lambda request: httpx.Response(200, content=b'[' * 20000 + b'0' + b']' * 20000))
    response = await client.post(path + 'test_connection/', headers=headers)
    assert response.status_code == 400 and response.json()['status'] == 'failed'


@pytest.mark.asyncio
async def test_deep_tool_arguments_are_unverified_not_internal_error(rbac_client, monkeypatch):
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    def reply(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': 'default'}]})
        data = json.loads(request.content)
        if 'tools' not in data:
            return httpx.Response(200, json={'choices': [{'message': {'content': 'answer'}}]})
        return httpx.Response(200, json={'choices': [{'message': {'tool_calls': [{'id': 'call', 'type': 'function', 'function': {'name': data['tools'][0]['function']['name'], 'arguments': '[' * 20000 + '0' + ']' * 20000}}]}}]})
    network(monkeypatch, reply)
    response = await client.get(path + 'models/', headers=headers)
    assert response.status_code == 200
    assert response.json()['recommendation']['verified']
    assert not response.json()['recommendation']['supports_tool_calling']


@pytest.mark.asyncio
async def test_change_and_revert_provider_configuration_still_invalidates_inflight_result(rbac_client, monkeypatch):
    from datetime import datetime
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    entered, gate = asyncio.Event(), asyncio.Event()
    async def reply(request):
        entered.set()
        await gate.wait()
        return httpx.Response(200, json={'choices': [{'message': {'content': 'answer'}}]})
    network(monkeypatch, reply)
    pending = asyncio.create_task(client.post(path + 'test_connection/', headers=headers))
    await asyncio.wait_for(entered.wait(), 2)
    previous = datetime.fromisoformat((await client.get(path, headers=headers)).json()['updated_at'])
    for url in ['https://other.example.com/v1', 'https://example.com/v1']:
        changed = await client.patch(path, headers=headers, json={'base_url': url})
        assert changed.status_code == 200
        current = datetime.fromisoformat(changed.json()['updated_at'])
        assert (current - previous).total_seconds() >= 1
        previous = current
    gate.set()
    assert (await pending).status_code == 409
    assert (await client.get(path, headers=headers)).json()['last_test_status'] == 'unknown'


@pytest.mark.asyncio
async def test_concurrent_tests_of_unchanged_configuration_can_both_save(rbac_client, monkeypatch):
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    entered, first_gate = asyncio.Event(), asyncio.Event()
    calls = 0
    async def reply(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await first_gate.wait()
        return httpx.Response(200, json={'choices': [{'message': {'content': 'answer'}}]})
    network(monkeypatch, reply)
    first = asyncio.create_task(client.post(path + 'test_connection/', headers=headers))
    await asyncio.wait_for(entered.wait(), 2)
    second = await client.post(path + 'test_connection/', headers=headers)
    first_gate.set()
    assert second.status_code == 200 and (await first).status_code == 200


@pytest.mark.asyncio
async def test_directory_remote_failure_without_fallback_still_records_safe_audit(rbac_client, monkeypatch, memory_session):
    from sqlalchemy import select
    from eventwall.models import EventRecord
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    assert (await client.patch(path, headers=headers, json={'default_model': '', 'backup_model': ''})).status_code == 200
    network(monkeypatch, lambda request: httpx.Response(401, json={'error': 'test-secret'}))
    response = await client.get(path + 'models/?probe=false', headers=headers)
    assert response.status_code == 400 and 'test-secret' not in response.text
    event = await memory_session.scalar(select(EventRecord).where(EventRecord.action == 'list_provider_models'))
    assert event is not None
    assert event.event_metadata['result'] == 'failed' and event.event_metadata['request_count'] == 1


@pytest.mark.asyncio
async def test_probe_verifies_text_and_harmless_tool_declaration(rbac_client, monkeypatch):
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    requests = []
    def reply(request):
        requests.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': 'default'}, {'id': 'backup'}]})
        data = json.loads(request.content)
        if 'tools' in data:
            name = data['tools'][0]['function']['name']
            return httpx.Response(200, json={'choices': [{'message': {'tool_calls': [{'id': 'call', 'type': 'function', 'function': {'name': name, 'arguments': '{"ok":true}'}}]}}]})
        return httpx.Response(200, json={'choices': [{'message': {'content': 'OK'}}]})
    network(monkeypatch, reply)
    result = await client.get(path + 'models/', headers=headers)
    assert result.status_code == 200
    recommendation = result.json()['recommendation']
    assert recommendation['verified'] and recommendation['supports_tool_calling']
    assert recommendation['requested_model'] == 'default'
    assert len(requests) <= 5
    assert (await client.get(path, headers=headers)).json()['default_model'] == 'default'


@pytest.mark.asyncio
async def test_catalog_failure_uses_safe_fallback_without_claiming_verification(rbac_client, monkeypatch):
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    network(monkeypatch, lambda request: httpx.Response(401, json={'error': 'test-secret'}))
    result = await client.get(path + 'models/?probe=false', headers=headers)
    assert result.status_code == 200
    assert result.json()['fallback_used'] and result.json()['recommendation'] is None
    assert result.json()['models'] == [{'id': 'default'}, {'id': 'backup'}]
    assert 'test-secret' not in result.text


@pytest.mark.asyncio
async def test_remote_failure_is_safe_and_saved_as_failed(rbac_client, monkeypatch):
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    network(monkeypatch, lambda request: httpx.Response(401, json={'error': 'test-secret'}))
    response = await client.post(path + 'test_connection/', headers=headers)
    assert response.status_code == 400 and response.json()['status'] == 'failed'
    assert 'test-secret' not in response.text
    assert (await client.get(path, headers=headers)).json()['last_test_status'] == 'failed'


@pytest.mark.asyncio
async def test_runtime_requires_manager_permission_and_valid_probe(rbac_client, monkeypatch, memory_session):
    from rbac.models import User
    from rbac.services.accounts import issue_token
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    user = User(username='runtime-unprivileged', password_hash='unused')
    memory_session.add(user)
    await memory_session.flush()
    token = await issue_token(memory_session, user)
    await memory_session.commit()
    for suffix, method in [('models/', client.get), ('test_connection/', client.post)]:
        assert (await method(path + suffix)).status_code == 401
        assert (await method(path + suffix, headers={'Authorization': 'Token ' + token})).status_code == 403
    assert (await client.get(path + 'models/?probe=invalid', headers=headers)).status_code == 422
    assert (await client.post(ROOT + '999/test_connection/', headers=headers)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['base_url', 'delete'])
async def test_changed_or_deleted_config_during_request_returns_conflict(rbac_client, monkeypatch, change):
    client, headers, _ = rbac_client
    path = await provider(client, headers, monkeypatch)
    entered, gate = asyncio.Event(), asyncio.Event()
    async def reply(request):
        entered.set()
        await gate.wait()
        return httpx.Response(200, json={'choices': [{'message': {'content': 'answer'}}]})
    network(monkeypatch, reply)
    pending = asyncio.create_task(client.post(path + 'test_connection/', headers=headers))
    await asyncio.wait_for(entered.wait(), 2)
    if change == 'delete':
        assert (await client.delete(path, headers=headers)).status_code == 204
    else:
        assert (await client.patch(path, headers=headers, json={'base_url': 'https://other.example.com/v1'})).status_code == 200
    gate.set()
    assert (await pending).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', ['missing_key', 'corrupt_key', 'disabled', 'private'])
async def test_setup_and_admission_failures_never_call_network_or_update_test_record(rbac_client, monkeypatch, invalid):
    client, headers, app = rbac_client
    path = await provider(client, headers, monkeypatch)
    if invalid == 'missing_key':
        monkeypatch.setenv('AIOPS_CONFIG_ENCRYPTION_KEY', '')
        expected = 503
    elif invalid == 'corrupt_key':
        monkeypatch.setenv('AIOPS_CONFIG_ENCRYPTION_KEY', Fernet.generate_key().decode())
        expected = 400
    else:
        values = {'is_enabled': False} if invalid == 'disabled' else {'base_url': 'https://127.0.0.1/v1'}
        assert (await client.patch(path, headers=headers, json=values)).status_code == 200
        expected = 400
    calls = []
    network(monkeypatch, lambda request: calls.append(request) or httpx.Response(200, json={}))
    response = await client.post(path + 'test_connection/', headers=headers)
    assert response.status_code == expected and not calls
    assert (await client.get(path, headers=headers)).json()['last_test_status'] == 'unknown'
