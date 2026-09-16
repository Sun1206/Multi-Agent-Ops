"""验证旧智能助手会话接口，隔离数据库且不访问模型。"""

import pytest
from sqlalchemy import select

from aiops.models import AIOpsChatMessage, AIOpsChatSession
from rbac.models import User
from rbac.services.accounts import issue_token
from tests_fastapi.integration.test_rbac_reads import rbac_client

ROOT = '/api/aiops/sessions/'


@pytest.mark.asyncio
async def test_bootstrap_legacy_shape_does_not_initialize_database(rbac_client, memory_session):
    client, headers, _ = rbac_client
    from aiops.models import AIOpsAgentConfig, AIOpsSkill
    result = await client.get('/api/aiops/bootstrap/', headers=headers)
    assert result.status_code == 200
    data = result.json()
    assert data['enabled'] is True
    assert set(data) == {'enabled', 'welcome_message', 'suggested_questions', 'action_registry', 'action_registry_summary', 'permissions', 'provider', 'runtime', 'active_mcp_servers', 'active_skills'}
    assert data['permissions']['chat'] is True and data['runtime']['allow_action_execution'] is False
    assert data['active_mcp_servers'] == [] and data['active_skills'] == []
    assert not list((await memory_session.scalars(select(AIOpsAgentConfig))).all())
    assert not list((await memory_session.scalars(select(AIOpsSkill))).all())


@pytest.mark.asyncio
async def test_context_aliases_and_pagination(rbac_client):
    client, headers, _ = rbac_client
    for i in range(23):
        response = await client.post(ROOT, headers=headers, json={'title': f'session-{i}', 'page_context': {'path': '/hosts', 'query': {'env': 'prod', 'application': 'api'}, 'suggested_questions': [' question ', 'question']}})
        assert response.status_code == 201
    context = response.json()['context']['page_context']
    assert context['route'] == '/hosts'
    assert context['hints'] == {'environment': 'prod', 'service': 'api'}
    assert context['suggested_questions'] == ['question']
    result = await client.get(ROOT, headers=headers, params={'page': 2, 'page_size': 10})
    assert result.status_code == 200
    assert result.json()['count'] == 23 and len(result.json()['results']) == 10
    assert 'page=3' in result.json()['next'] and 'page=1' in result.json()['previous']
    assert (await client.get(ROOT, headers=headers, params={'page': 4, 'page_size': 10})).status_code == 404


@pytest.mark.asyncio
async def test_existing_message_metadata_is_safely_serialized(rbac_client, memory_session):
    client, headers, _ = rbac_client
    response = await client.post(ROOT, headers=headers, json={})
    identifier = response.json()['id']
    memory_session.add(AIOpsChatMessage(session_id=identifier, role='assistant', content='waiting', metadata_data={'processing_status': 'pending', 'processing_text': 'waiting', 'page_context': {'query': {'api_key': 'private-key'}}, 'error_detail': 'private-remote-error', 'response_blocks': [{'type': 'approval_form'}]}))
    await memory_session.commit()
    result = await client.get(ROOT + f'{identifier}/messages/', headers=headers)
    assert result.status_code == 200
    assert result.json()[0]['metadata']['processing_status'] == 'pending'
    assert 'private-key' not in result.text and 'private-remote-error' not in result.text
    assert result.json()[0]['blocks'] == [] and result.json()[0]['pending_action'] is None


@pytest.mark.asyncio
async def test_session_legacy_contract_and_delete(rbac_client):
    client, headers, _ = rbac_client
    created = await client.post(ROOT, headers=headers, json={'title': '', 'page_context': {'path': '/hosts', 'title': 'Hosts'}})
    assert created.status_code == 201
    item = created.json()
    assert item['title'] == '新会话' and item['latest_message'] is None
    assert set(item) == {'id', 'title', 'status', 'context', 'last_message_at', 'created_at', 'updated_at', 'latest_message'}
    path = ROOT + str(item['id']) + '/'
    assert (await client.get(path, headers=headers)).json() == item
    listing = (await client.get(ROOT, headers=headers)).json()
    assert set(listing) == {'count', 'next', 'previous', 'results'}
    assert listing['count'] == 1 and listing['results'][0]['id'] == item['id']
    assert (await client.get(path + 'messages/', headers=headers)).json() == []
    assert (await client.post(path + 'delete_session/', headers=headers)).status_code == 204
    missing = await client.get(path, headers=headers)
    assert missing.status_code == 404 and '会话不存在' in missing.json()['detail']


@pytest.mark.asyncio
async def test_full_message_array_preserves_legacy_fields(rbac_client, memory_session):
    client, headers, _ = rbac_client
    response = await client.post(ROOT, headers=headers, json={})
    assert response.status_code == 201
    identifier = response.json()['id']
    memory_session.add_all([AIOpsChatMessage(session_id=identifier, role='user', content=f'message-{i}') for i in range(505)])
    await memory_session.commit()
    result = await client.get(ROOT + f'{identifier}/messages/', headers=headers)
    assert result.status_code == 200 and len(result.json()) == 505
    assert result.json()[0]['content'] == 'message-0'
    assert set(result.json()[0]) == {'id', 'role', 'message_type', 'content', 'citations', 'tool_calls', 'metadata', 'blocks', 'pending_action', 'created_at'}
    latest = (await client.get(ROOT, headers=headers)).json()['results'][0]['latest_message']
    assert latest['content'] == 'message-504'
    assert (await client.delete(ROOT + f'{identifier}/', headers=headers)).status_code == 204
    assert not list((await memory_session.scalars(select(AIOpsChatMessage))).all())


@pytest.mark.asyncio
async def test_superuser_cannot_access_other_users_sessions(rbac_client, memory_session):
    client, headers, _ = rbac_client
    user = User(username='other-chat-user', password_hash='unused')
    memory_session.add(user)
    await memory_session.flush()
    session = AIOpsChatSession(user_id=user.id)
    memory_session.add(session)
    await memory_session.commit()
    path = ROOT + str(session.id) + '/'
    for suffix in ('', 'messages/'):
        assert (await client.get(path + suffix, headers=headers)).status_code == 404
    assert (await client.post(path + 'delete_session/', headers=headers)).status_code == 404
    assert (await client.get(ROOT, headers=headers)).json()['count'] == 0


@pytest.mark.asyncio
async def test_sessions_require_chat_permission(rbac_client, memory_session):
    client, _, _ = rbac_client
    assert (await client.get(ROOT)).status_code == 401
    user = User(username='no-chat-permission', password_hash='unused')
    memory_session.add(user)
    await memory_session.flush()
    token = await issue_token(memory_session, user)
    await memory_session.commit()
    headers = {'Authorization': f'Token {token}'}
    assert (await client.get(ROOT, headers=headers)).status_code == 403
    assert (await client.post(ROOT, headers=headers, json={})).status_code == 403


@pytest.mark.asyncio
async def test_invalid_title_does_not_create_session(rbac_client):
    client, headers, _ = rbac_client
    assert (await client.post(ROOT, headers=headers, json={'title': 'x' * 129})).status_code == 422
    assert (await client.get(ROOT, headers=headers)).json()['count'] == 0


@pytest.mark.asyncio
async def test_delete_audit_failure_rolls_back(rbac_client, memory_session, monkeypatch):
    client, headers, _ = rbac_client
    created = await client.post(ROOT, headers=headers, json={})
    assert created.status_code == 201
    from aiops.services import chat
    async def fail(*args, **kwargs):
        raise RuntimeError('audit unavailable')
    monkeypatch.setattr(chat, 'record_event', fail)
    path = ROOT + str(created.json()['id']) + '/'
    assert (await client.post(path + 'delete_session/', headers=headers)).status_code == 500
    assert (await client.get(path, headers=headers)).status_code == 200
