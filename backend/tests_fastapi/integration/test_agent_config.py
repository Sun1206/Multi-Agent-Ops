import json

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from aiops.models import AIOpsAgentConfig, AIOpsMCPServer, AIOpsModelProvider, AIOpsSkill
from eventwall.models import EventRecord
from test_rbac_reads import rbac_client


ROOT = '/api/aiops/admin/'


@pytest.fixture
def config_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv('AIOPS_CONFIG_ENCRYPTION_KEY', key)
    return key


async def create(client, headers, kind, body):
    response = await client.post(ROOT + kind + '/', headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_core_reads_are_readonly_and_runtime_not_implemented(rbac_client):
    client, headers, app = rbac_client
    for path in ['config/', 'actions/', 'providers/', 'providers/presets/', 'mcp-servers/', 'skills/', 'skills/marketplace/']:
        response = await client.get(ROOT + path, headers=headers)
        assert response.status_code == 200, (path, response.text)
    actions = (await client.get(ROOT + 'actions/', headers=headers)).json()
    assert len(actions['actions']) == 7 and all(not item['available'] for item in actions['actions'])
    assert len((await client.get(ROOT + 'providers/presets/', headers=headers)).json()['presets']) == 8
    async with app.state.session_factory() as session:
        assert await session.scalar(select(AIOpsAgentConfig)) is None
        assert await session.scalar(select(EventRecord)) is None
    assert (await client.post(ROOT + 'providers/1/test_connection/', headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_provider_config_and_reference_cleanup(rbac_client, config_key):
    client, headers, app = rbac_client
    provider = await create(client, headers, 'providers', {'name': 'test-provider', 'base_url': 'https://example.com/v1', 'default_model': 'model', 'api_key': 'provider-secret'})
    assert provider['has_api_key'] and provider['runtime_ready'] and provider['last_test_status'] == 'unknown'
    assert 'provider-secret' not in json.dumps(provider)
    url = ROOT + 'providers/' + str(provider['id']) + '/'
    edited = await client.patch(url, headers=headers, json={**provider, 'name': 'renamed'})
    assert edited.status_code == 200 and edited.json()['has_api_key']
    config = await client.put(ROOT + 'config/', headers=headers, json={'default_provider_id': provider['id'], 'system_prompt': 'prompt-private', 'require_confirmation': True})
    assert config.status_code == 200 and config.json()['default_provider']['id'] == provider['id']
    config = await client.put(ROOT + 'config/', headers=headers, json={'welcome_message': '您好'})
    assert config.json()['system_prompt'] == 'prompt-private'
    async with app.state.session_factory() as session:
        stored = await session.get(AIOpsModelProvider, provider['id'])
        assert stored.api_key_encrypted != 'provider-secret'
        assert Fernet(config_key.encode()).decrypt(stored.api_key_encrypted.encode()) == b'provider-secret'
        events = list((await session.scalars(select(EventRecord))).all())
        assert all(event.module == 'aiops' for event in events)
        assert 'provider-secret' not in str([e.event_metadata for e in events])
        assert 'prompt-private' not in str([e.event_metadata for e in events])
    assert (await client.get(url, headers=headers)).status_code == 200
    assert (await client.delete(url, headers=headers)).status_code == 204
    assert (await client.get(ROOT + 'config/', headers=headers)).json()['default_provider'] is None
    assert (await client.get(url, headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_skill_clone_and_selected_relation_cleanup(rbac_client):
    client, headers, _ = rbac_client
    skill = await create(client, headers, 'skills', {'name': '团队Skill', 'slug': 'team-skill', 'content': 'private-skill-content', 'applicable_actions': ['alert.root_cause'], 'allowed_role_codes': ['platform-admin']})
    url = ROOT + f"skills/{skill['id']}/"
    cloned = await client.post(url + 'clone/', headers=headers, json={})
    assert cloned.status_code == 201, cloned.text
    assert cloned.json()['id'] != skill['id'] and not cloned.json()['is_builtin']
    market = (await client.get(ROOT + 'skills/marketplace/', headers=headers)).json()
    assert market['summary']['total'] == 2 and len(market['items']) == 2
    assert (await client.put(ROOT + 'config/', headers=headers, json={'enabled_skill_ids': [skill['id'], skill['id']]})).json()['enabled_skill_ids'] == [skill['id']]
    assert (await client.patch(url, headers=headers, json={'recommended_tools': [], 'is_enabled': False})).status_code == 200
    assert (await client.get(url, headers=headers)).json()['content'] == 'private-skill-content'
    assert (await client.delete(url, headers=headers)).status_code == 204
    assert (await client.get(ROOT + 'config/', headers=headers)).json()['enabled_skill_ids'] == []


@pytest.mark.asyncio
async def test_mcp_secret_mask_roundtrip_clear_and_cleanup(rbac_client, config_key):
    client, headers, app = rbac_client
    mcp = await create(client, headers, 'mcp-servers', {'name': 'test-mcp', 'endpoint_or_command': 'https://example.com/mcp', 'auth_config': {'headers': {'Authorization': 'Bearer mcp-secret'}, 'env': {'TOKEN': 'env-secret'}, 'allow_write': False, 'timeout_seconds': 30}})
    assert mcp['auth_config']['headers']['Authorization'] == '***'
    url = ROOT + f"mcp-servers/{mcp['id']}/"
    assert (await client.patch(url, headers=headers, json={**mcp, 'description': 'changed'})).status_code == 200
    async with app.state.session_factory() as session:
        stored = await session.get(AIOpsMCPServer, mcp['id'])
        assert 'mcp-secret' not in json.dumps(stored.auth_config) and 'env-secret' not in json.dumps(stored.auth_config)
        assert stored.auth_config['allow_write'] is False
    assert (await client.put(ROOT + 'config/', headers=headers, json={'enabled_mcp_server_ids': [mcp['id']]})).status_code == 200
    assert (await client.patch(url, headers=headers, json={'auth_config': {}})).json()['auth_config'] == {}
    assert (await client.delete(url, headers=headers)).status_code == 204
    assert (await client.get(ROOT + 'config/', headers=headers)).json()['enabled_mcp_server_ids'] == []


@pytest.mark.asyncio
async def test_missing_encryption_key_does_not_block_nonsecret_config(rbac_client, monkeypatch):
    monkeypatch.delenv('AIOPS_CONFIG_ENCRYPTION_KEY', raising=False)
    client, headers, _ = rbac_client
    await create(client, headers, 'providers', {'name': 'no-key-provider'})
    response = await client.post(ROOT + 'providers/', headers=headers, json={'name': 'with-secret', 'api_key': 'hidden-key'})
    assert response.status_code == 503 and 'hidden-key' not in response.text
    assert len((await client.get(ROOT + 'providers/', headers=headers)).json()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,body,status', [
    ('providers', {'name': ''}, 422),
    ('providers', {'name': 'x', 'base_url': 'https://user:pass@example.com'}, 422),
    ('providers', {'name': 'x', 'api_key_encrypted': 'forged'}, 422),
    ('providers', {'name': 'x', 'temperature': 3}, 422),
    ('providers', {'name': 'x', 'input_token_price_per_1m': -1}, 422),
    ('providers', {'name': 'x', 'api_key': '   '}, 422),
    ('skills', {'name': 'x', 'slug': 'x', 'applicable_actions': ['unregistered']}, 400),
    ('skills', {'name': 'x', 'slug': 'x', 'allowed_role_codes': ['unknown']}, 400),
    ('skills', {'name': 'x', 'slug': 'x', 'output_contract': []}, 422),
    ('skills', {'name': 'x', 'slug': 'x', 'max_iterations': 21}, 422),
    ('mcp-servers', {'name': 'x', 'server_type': 'platform_builtin'}, 400),
    ('mcp-servers', {'name': 'x', 'auth_config': {'headers': {'Authorization': '***'}}}, 400),
    ('mcp-servers', {'name': 'x', 'auth_config': {'token': {'__aiops_secret_v1__': 'forged'}}}, 400),
])
async def test_invalid_creation_is_atomic(rbac_client, config_key, kind, body, status):
    client, headers, _ = rbac_client
    response = await client.post(ROOT + kind + '/', headers=headers, json=body)
    assert response.status_code == status, response.text
    assert (await client.get(ROOT + kind + '/', headers=headers)).json() == []


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [{'require_confirmation': False}, {'default_provider_id': 999}, {'enabled_skill_ids': [999]}, {'enabled_mcp_server_ids': [999]}])
async def test_invalid_strategy_does_not_create_default_record(rbac_client, body):
    client, headers, app = rbac_client
    response = await client.put(ROOT + 'config/', headers=headers, json=body)
    assert response.status_code == 400
    async with app.state.session_factory() as session:
        assert await session.scalar(select(AIOpsAgentConfig)) is None


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_and_builtin_protected(rbac_client):
    from aiops.services.agent_config import bootstrap_agent_catalog

    client, headers, app = rbac_client
    async with app.state.session_factory() as session:
        await bootstrap_agent_catalog(session)
        await session.commit()
        await bootstrap_agent_catalog(session)
        await session.commit()
    skills = (await client.get(ROOT + 'skills/', headers=headers)).json()
    assert len(skills) == 13
    for kind, item, patch in [('skills', skills[0], {'slug': 'renamed-builtin'}), ('mcp-servers', (await client.get(ROOT + 'mcp-servers/', headers=headers)).json()[0], {'name': 'renamed-builtin'})]:
        url = ROOT + f"{kind}/{item['id']}/"
        assert (await client.patch(url, headers=headers, json=patch)).status_code == 400
        assert (await client.delete(url, headers=headers)).status_code == 400


@pytest.mark.asyncio
async def test_config_audit_failure_rolls_back(rbac_client, monkeypatch):
    import aiops.services.agent_config as service

    client, headers, _ = rbac_client
    async def fail(*args, **kwargs):
        raise RuntimeError('private-internal-error')
    monkeypatch.setattr(service, 'record_event', fail)
    response = await client.post(ROOT + 'skills/', headers=headers, json={'name': 'rollback', 'slug': 'rollback'})
    assert response.status_code == 500 and 'private-internal-error' not in response.text
    assert (await client.get(ROOT + 'skills/', headers=headers)).json() == []


@pytest.mark.asyncio
async def test_config_routes_require_auth(rbac_client):
    client, _, _ = rbac_client
    assert (await client.get(ROOT + 'config/')).status_code == 401
    assert (await client.post(ROOT + 'providers/', json={'name': 'x'})).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize('code', ['aiops.config.view', 'aiops.config.manage', None])
async def test_config_permissions_do_not_expand_identity(rbac_client, memory_session, code):
    from rbac.models import PermissionDefinition, Role, User
    from rbac.services.accounts import issue_token

    client, _, _ = rbac_client
    roles = []
    if code:
        permission = await memory_session.scalar(select(PermissionDefinition).where(PermissionDefinition.code == code))
        roles = [Role(name='config-role', code='config-role', permissions=[permission])]
    user = User(username='config-user', password_hash='unused', roles=roles)
    memory_session.add(user)
    await memory_session.flush()
    token = await issue_token(memory_session, user)
    await memory_session.commit()
    headers = {'Authorization': f'Token {token}'}
    assert (await client.get(ROOT + 'config/', headers=headers)).status_code == (200 if code == 'aiops.config.view' else 403)
    assert (await client.post(ROOT + 'skills/', headers=headers, json={'name': 'test', 'slug': 'test'})).status_code == (201 if code == 'aiops.config.manage' else 403)
    assert not user.is_superuser and not user.is_staff


@pytest.mark.asyncio
async def test_provider_connection_change_invalidates_previous_test(rbac_client, memory_session, config_key):
    client, headers, _ = rbac_client
    provider = await create(client, headers, 'providers', {'name': 'test', 'api_key': 'test-key'})
    stored = await memory_session.get(AIOpsModelProvider, provider['id'])
    stored.last_test_status = 'success'
    stored.last_test_message = 'private-remote-message'
    await memory_session.commit()
    response = await client.patch(ROOT + f"providers/{provider['id']}/", headers=headers, json={'timeout_seconds': 60, 'last_test_status': 'success'})
    assert response.status_code == 200
    assert response.json()['last_test_status'] == 'unknown'
    assert response.json()['last_test_message'] == ''


@pytest.mark.asyncio
async def test_provider_clear_key_and_uniqueness(rbac_client, config_key):
    client, headers, _ = rbac_client
    provider = await create(client, headers, 'providers', {'name': 'duplicate', 'api_key': 'test-key'})
    assert (await client.post(ROOT + 'providers/', headers=headers, json={'name': 'duplicate'})).status_code == 409
    response = await client.patch(ROOT + f"providers/{provider['id']}/", headers=headers, json={'api_key': ''})
    assert response.status_code == 200 and not response.json()['has_api_key']
    assert len((await client.get(ROOT + 'providers/', headers=headers)).json()) == 1


@pytest.mark.asyncio
async def test_existing_mcp_mask_preserves_exact_cipher_and_rotation(rbac_client, config_key):
    client, headers, app = rbac_client
    mcp = await create(client, headers, 'mcp-servers', {'name': 'test', 'auth_config': {'headers': {'Authorization': 'first-secret'}}})
    async with app.state.session_factory() as session:
        original = (await session.get(AIOpsMCPServer, mcp['id'])).auth_config
    url = ROOT + f"mcp-servers/{mcp['id']}/"
    assert (await client.patch(url, headers=headers, json={'auth_config': mcp['auth_config']})).status_code == 200
    async with app.state.session_factory() as session:
        assert (await session.get(AIOpsMCPServer, mcp['id'])).auth_config == original
    assert (await client.patch(url, headers=headers, json={'auth_config': {'headers': {'Authorization': 'rotated-secret'}}})).status_code == 200
    async with app.state.session_factory() as session:
        rotated = (await session.get(AIOpsMCPServer, mcp['id'])).auth_config
        assert rotated != original and 'rotated-secret' not in json.dumps(rotated)
    assert (await client.patch(url, headers=headers, json={'auth_config': {'headers': {'New-Token': '***'}}})).status_code == 400


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_secret_and_event(rbac_client, config_key, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    client, headers, app = rbac_client
    async def fail_commit(session):
        await session.flush()
        raise RuntimeError('private-commit-error')
    monkeypatch.setattr(AsyncSession, 'commit', fail_commit)
    response = await client.post(ROOT + 'providers/', headers=headers, json={'name': 'rollback', 'api_key': 'rollback-secret'})
    assert response.status_code == 500 and 'rollback-secret' not in response.text
    async with app.state.session_factory() as session:
        assert await session.scalar(select(AIOpsModelProvider)) is None
        assert await session.scalar(select(EventRecord)) is None
def test_catalog_has_valid_unicode():
    """内置目录不能包含解码损失字符，避免初始化损坏内容。"""
    import json
    from aiops.agent_registry import CATALOG
    assert '\ufffd' not in json.dumps(CATALOG, ensure_ascii=False)


@pytest.mark.asyncio
async def test_virtual_strategy_defaults_survive_first_partial_save(rbac_client):
    """首次局部保存不能改变未提交的欢迎语。"""
    client, headers, _ = rbac_client
    before = (await client.get(ROOT + 'config/', headers=headers)).json()
    after = await client.put(ROOT + 'config/', headers=headers, json={'system_prompt': 'test'})
    assert after.status_code == 200
    assert after.json()['welcome_message'] == before['welcome_message']
