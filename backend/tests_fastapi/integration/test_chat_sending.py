import asyncio

import pytest
from cryptography.fernet import Fernet

from tests_fastapi.integration.test_rbac_reads import rbac_client


ROOT = '/api/aiops/sessions/'


async def configure(client, headers, monkeypatch):
    monkeypatch.setenv('AIOPS_CONFIG_ENCRYPTION_KEY', Fernet.generate_key().decode())
    provider = await client.post('/api/aiops/admin/providers/', headers=headers, json={'name': 'chat-model', 'base_url': 'https://example.com/v1', 'default_model': 'model', 'api_key': 'test-key'})
    assert provider.status_code == 201
    assert (await client.put('/api/aiops/admin/config/', headers=headers, json={'default_provider_id': provider.json()['id']})).status_code == 200


@pytest.mark.asyncio
async def test_async_pending_response_then_real_text_result(rbac_client, monkeypatch):
    client, headers, app = rbac_client
    await configure(client, headers, monkeypatch)
    from aiops.services import model_client
    gate = asyncio.Event()
    calls = []
    async def reply(target, key, payload, timeout_seconds):
        calls.append(payload)
        await gate.wait()
        return 'test answer'
    monkeypatch.setattr(model_client, 'request_text', reply)
    created = await client.post(ROOT, headers=headers, json={})
    path = ROOT + str(created.json()['id']) + '/'
    response = await client.post(path + 'send_message_async/', headers=headers, json={'content': 'hello', 'analysis_only': True})
    assert response.status_code == 201
    data = response.json()
    assert data['assistant_message']['metadata']['processing_status'] == 'pending'
    assert data['user_message']['content'] == 'hello' and data['pending_action'] is None
    gate.set()
    await app.state.chat_jobs.wait_all()
    messages = (await client.get(path + 'messages/', headers=headers)).json()
    assert messages[-1]['content'] == 'test answer'
    assert messages[-1]['metadata']['processing_status'] == 'completed'
    assert messages[-1]['tool_calls'] == [] and messages[-1]['pending_action'] is None
    assert calls[0]['messages'][-1] == {'role': 'user', 'content': 'hello'}


@pytest.mark.asyncio
async def test_missing_model_finishes_failed_instead_of_stuck(rbac_client):
    client, headers, app = rbac_client
    created = await client.post(ROOT, headers=headers, json={})
    path = ROOT + str(created.json()['id']) + '/'
    response = await client.post(path + 'send_message_async/', headers=headers, json={'content': 'hello'})
    assert response.status_code == 201
    await app.state.chat_jobs.wait_all()
    messages = (await client.get(path + 'messages/', headers=headers)).json()
    assert len(messages) == 2 and messages[-1]['message_type'] == 'error'
    assert messages[-1]['metadata']['processing_status'] == 'failed'


@pytest.mark.asyncio
async def test_synchronous_compatibility_endpoint(rbac_client, monkeypatch):
    client, headers, _ = rbac_client
    await configure(client, headers, monkeypatch)
    from aiops.services import model_client
    async def reply(*args, **kwargs):
        return 'sync answer'
    monkeypatch.setattr(model_client, 'request_text', reply)
    created = await client.post(ROOT, headers=headers, json={})
    response = await client.post(ROOT + str(created.json()['id']) + '/send_message/', headers=headers, json={'content': 'hello'})
    assert response.status_code == 201
    assert response.json()['assistant_message']['content'] == 'sync answer'


@pytest.mark.asyncio
async def test_invalid_payload_never_queues(rbac_client):
    client, headers, _ = rbac_client
    created = await client.post(ROOT, headers=headers, json={})
    path = ROOT + str(created.json()['id']) + '/'
    for value in (' ', 'x' * 4001):
        assert (await client.post(path + 'send_message_async/', headers=headers, json={'content': value})).status_code == 422
    assert (await client.get(path + 'messages/', headers=headers)).json() == []


@pytest.mark.asyncio
async def test_delete_while_model_is_running_does_not_recreate_chat(rbac_client, monkeypatch):
    client, headers, app = rbac_client
    await configure(client, headers, monkeypatch)
    from aiops.services import model_client
    entered, gate = asyncio.Event(), asyncio.Event()
    async def reply(*args, **kwargs):
        entered.set()
        await gate.wait()
        return 'answer'
    monkeypatch.setattr(model_client, 'request_text', reply)
    created = await client.post(ROOT, headers=headers, json={})
    path = ROOT + str(created.json()['id']) + '/'
    assert (await client.post(path + 'send_message_async/', headers=headers, json={'content': 'hello'})).status_code == 201
    await asyncio.wait_for(entered.wait(), 2)
    assert (await client.post(path + 'delete_session/', headers=headers)).status_code == 204
    await asyncio.wait_for(app.state.chat_jobs.wait_all(), 0.2)
    assert (await client.get(path, headers=headers)).status_code == 404
    assert app.state.chat_jobs.pending == 0


@pytest.mark.asyncio
async def test_same_session_requests_are_ordered_and_use_completed_context(rbac_client, monkeypatch):
    client, headers, app = rbac_client
    await configure(client, headers, monkeypatch)
    from aiops.services import model_client
    gate, entered = asyncio.Event(), asyncio.Event()
    payloads = []
    async def reply(target, key, payload, timeout):
        payloads.append(payload)
        entered.set()
        await gate.wait()
        return 'reply-' + payload['messages'][-1]['content']
    monkeypatch.setattr(model_client, 'request_text', reply)
    created = await client.post(ROOT, headers=headers, json={})
    path = ROOT + str(created.json()['id']) + '/'
    assert (await client.post(path + 'send_message_async/', headers=headers, json={'content': 'first'})).status_code == 201
    await asyncio.wait_for(entered.wait(), 2)
    assert (await client.post(path + 'send_message_async/', headers=headers, json={'content': 'second'})).status_code == 201
    assert len(payloads) == 1
    gate.set()
    await app.state.chat_jobs.wait_all()
    assert len(payloads) == 2
    assert payloads[1]['messages'][-3:] == [{'role': 'user', 'content': 'first'}, {'role': 'assistant', 'content': 'reply-first'}, {'role': 'user', 'content': 'second'}]


@pytest.mark.asyncio
async def test_changed_model_configuration_rejects_old_answer(rbac_client, monkeypatch):
    client, headers, app = rbac_client
    await configure(client, headers, monkeypatch)
    from aiops.services import model_client
    gate, entered = asyncio.Event(), asyncio.Event()
    async def reply(*args):
        entered.set()
        await gate.wait()
        return 'old-answer'
    monkeypatch.setattr(model_client, 'request_text', reply)
    created = await client.post(ROOT, headers=headers, json={})
    path = ROOT + str(created.json()['id']) + '/'
    assert (await client.post(path + 'send_message_async/', headers=headers, json={'content': 'hello'})).status_code == 201
    await asyncio.wait_for(entered.wait(), 2)
    assert (await client.put('/api/aiops/admin/config/', headers=headers, json={'system_prompt': 'changed'})).status_code == 200
    gate.set()
    await app.state.chat_jobs.wait_all()
    messages = (await client.get(path + 'messages/', headers=headers)).json()
    assert messages[-1]['metadata']['processing_status'] == 'failed'
    assert 'old-answer' not in str(messages)


@pytest.mark.asyncio
async def test_queue_limit_rejects_before_message_write(rbac_client):
    client, headers, app = rbac_client
    app.state.chat_jobs.max_pending = 0
    created = await client.post(ROOT, headers=headers, json={})
    path = ROOT + str(created.json()['id']) + '/'
    assert (await client.post(path + 'send_message_async/', headers=headers, json={'content': 'hello'})).status_code == 429
    assert (await client.get(path + 'messages/', headers=headers)).json() == []


@pytest.mark.asyncio
async def test_interrupted_recovery_only_changes_this_worker_version(rbac_client, memory_session):
    client, headers, app = rbac_client
    from aiops.models import AIOpsChatMessage
    from aiops.services.chat_jobs import recover_interrupted, WORKER_TAG
    created = await client.post(ROOT, headers=headers, json={})
    identifier = created.json()['id']
    for tag in (WORKER_TAG, 'legacy'):
        memory_session.add(AIOpsChatMessage(session_id=identifier, role='assistant', content=tag, metadata_data={'worker_tag': tag, 'processing_status': 'pending'}))
    await memory_session.commit()
    await recover_interrupted(app.state.session_factory)
    messages = (await client.get(ROOT + f'{identifier}/messages/', headers=headers)).json()
    assert [message['metadata']['processing_status'] for message in messages] == ['failed', 'pending']


@pytest.mark.asyncio
async def test_scheduler_failure_marks_committed_placeholder_failed(rbac_client, monkeypatch):
    client, headers, app = rbac_client
    def fail(*args):
        raise RuntimeError('scheduler failure')
    monkeypatch.setattr(app.state.chat_jobs, 'start', fail)
    created = await client.post(ROOT, headers=headers, json={})
    path = ROOT + str(created.json()['id']) + '/'
    response = await client.post(path + 'send_message_async/', headers=headers, json={'content': 'hello'})
    assert response.status_code == 503
    messages = (await client.get(path + 'messages/', headers=headers)).json()
    assert messages[-1]['metadata']['processing_status'] == 'failed'
    assert app.state.chat_jobs.pending == 0


@pytest.mark.asyncio
async def test_immediately_cancelled_job_releases_admission(rbac_client):
    client, headers, app = rbac_client
    jobs = app.state.chat_jobs
    jobs.reserve()
    task = jobs.start(999, 999, 999, 999)
    task.cancel()
    await jobs.wait_all()
    assert jobs.pending == 0 and not jobs.tails


@pytest.mark.asyncio
async def test_submission_order_survives_delay_after_database_commit(rbac_client, monkeypatch):
    client, headers, app = rbac_client
    await configure(client, headers, monkeypatch)
    from sqlalchemy.ext.asyncio import AsyncSession
    from aiops.services import model_client
    created = await client.post(ROOT, headers=headers, json={})
    path = ROOT + str(created.json()['id']) + '/'
    committed, release = asyncio.Event(), asyncio.Event()
    original = AsyncSession.commit
    first = True
    async def delayed(database):
        nonlocal first
        delay = first
        first = False
        await original(database)
        if delay:
            committed.set()
            await release.wait()
    payloads = []
    async def reply(target, key, payload, timeout):
        payloads.append(payload['messages'][-1]['content'])
        return 'answer'
    monkeypatch.setattr(AsyncSession, 'commit', delayed)
    monkeypatch.setattr(model_client, 'request_text', reply)
    one = asyncio.create_task(client.post(path + 'send_message_async/', headers=headers, json={'content': 'first'}))
    await asyncio.wait_for(committed.wait(), 2)
    two = asyncio.create_task(client.post(path + 'send_message_async/', headers=headers, json={'content': 'second'}))
    # Let B attempt submission while A's commit return is deliberately suspended.
    try:
        await asyncio.wait_for(asyncio.shield(two), 0.2)
    except TimeoutError:
        pass
    release.set()
    assert [response.status_code for response in await asyncio.gather(one, two)] == [201, 201]
    await app.state.chat_jobs.wait_all()
    assert payloads == ['first', 'second']


@pytest.mark.asyncio
async def test_revoked_chat_permission_discards_inflight_answer(rbac_client, memory_session, monkeypatch):
    from sqlalchemy import select, insert, delete
    from rbac.models import User, Role, PermissionDefinition
    from rbac.models.authorization import user_roles, role_permissions
    from rbac.services.accounts import issue_token
    from aiops.services import model_client
    client, admin_headers, app = rbac_client
    await configure(client, admin_headers, monkeypatch)
    user = User(username='chat-reader', password_hash='unused')
    role = Role(name='chat-only', code='chat-only')
    memory_session.add_all([user, role])
    await memory_session.flush()
    permission = await memory_session.scalar(select(PermissionDefinition).where(PermissionDefinition.code == 'aiops.chat.view'))
    await memory_session.execute(insert(user_roles).values(user_id=user.id, role_id=role.id))
    await memory_session.execute(insert(role_permissions).values(role_id=role.id, permission_id=permission.id))
    raw = await issue_token(memory_session, user)
    await memory_session.commit()
    headers = {'Authorization': 'Token ' + raw}
    entered, gate = asyncio.Event(), asyncio.Event()
    async def reply(*args):
        entered.set()
        await gate.wait()
        return 'revoked-answer'
    monkeypatch.setattr(model_client, 'request_text', reply)
    created = await client.post(ROOT, headers=headers, json={})
    path = ROOT + str(created.json()['id']) + '/'
    assert (await client.post(path + 'send_message_async/', headers=headers, json={'content': 'hello'})).status_code == 201
    await asyncio.wait_for(entered.wait(), 2)
    await memory_session.execute(delete(user_roles).where(user_roles.c.user_id == user.id))
    await memory_session.commit()
    gate.set()
    await app.state.chat_jobs.wait_all()
    from aiops.models import AIOpsChatMessage
    memory_session.expire_all()
    messages = list((await memory_session.scalars(select(AIOpsChatMessage).where(AIOpsChatMessage.session_id == created.json()['id']).order_by(AIOpsChatMessage.id))).all())
    assert messages[-1].metadata_data['processing_status'] == 'failed'
    assert messages[-1].content != 'revoked-answer'


@pytest.mark.asyncio
async def test_model_origin_allowlist_uses_dotenv_when_environment_absent(rbac_client, monkeypatch):
    from aiops.services import chat_jobs
    client, headers, app = rbac_client
    await configure(client, headers, monkeypatch)
    providers = (await client.get('/api/aiops/admin/providers/', headers=headers)).json()
    assert (await client.patch('/api/aiops/admin/providers/' + str(providers[0]['id']) + '/', headers=headers, json={'base_url': 'http://localhost:11434/v1'})).status_code == 200
    monkeypatch.delenv('AIOPS_MODEL_ALLOWED_INTERNAL_ORIGINS', raising=False)
    monkeypatch.setattr(chat_jobs, 'dotenv_values', lambda path: {'AIOPS_MODEL_ALLOWED_INTERNAL_ORIGINS': '["http://localhost:11434"]'}, raising=False)
    created = await client.post(ROOT, headers=headers, json={})
    from aiops.models import AIOpsChatMessage
    async with app.state.session_factory() as database:
        message = AIOpsChatMessage(session_id=created.json()['id'], role='user', content='hello')
        database.add(message)
        await database.commit()
        identifier = message.id
    actor = (await client.get('/api/users/', headers=headers)).json()['results'][0]['id']
    _, _, target, _, _ = await chat_jobs.prepare_request(app.state.session_factory, created.json()['id'], identifier, actor)
    assert target.internal_allowed


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['audit', 'commit'])
async def test_submission_transaction_failure_never_starts_worker(rbac_client, monkeypatch, failure):
    from aiops.api import chat
    from sqlalchemy.ext.asyncio import AsyncSession
    client, headers, app = rbac_client
    created = await client.post(ROOT, headers=headers, json={})
    path = ROOT + str(created.json()['id']) + '/'
    async def fail(*args, **kwargs):
        raise RuntimeError('transaction failure')
    with monkeypatch.context() as patch:
        patch.setattr(chat if failure == 'audit' else AsyncSession, 'audit_chat' if failure == 'audit' else 'commit', fail)
        response = await client.post(path + 'send_message_async/', headers=headers, json={'content': 'hello'})
    assert response.status_code == 500
    assert (await client.get(path + 'messages/', headers=headers)).json() == []
    assert app.state.chat_jobs.pending == 0 and not app.state.chat_jobs.tasks


@pytest.mark.asyncio
async def test_completed_transaction_failure_does_not_publish_answer(rbac_client, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    from aiops.models import AIOpsChatMessage
    from aiops.services import model_client
    client, headers, app = rbac_client
    await configure(client, headers, monkeypatch)
    original = AsyncSession.commit
    async def fail_completed(database):
        if any(isinstance(message, AIOpsChatMessage) and message.metadata_data.get('processing_status') == 'completed' for message in database.identity_map.values()):
            raise RuntimeError('terminal commit failure')
        await original(database)
    async def reply(*args):
        return 'uncommitted-answer'
    monkeypatch.setattr(AsyncSession, 'commit', fail_completed)
    monkeypatch.setattr(model_client, 'request_text', reply)
    created = await client.post(ROOT, headers=headers, json={})
    path = ROOT + str(created.json()['id']) + '/'
    assert (await client.post(path + 'send_message_async/', headers=headers, json={'content': 'hello'})).status_code == 201
    await app.state.chat_jobs.wait_all()
    messages = (await client.get(path + 'messages/', headers=headers)).json()
    assert messages[-1]['metadata']['processing_status'] == 'failed'
    assert 'uncommitted-answer' not in str(messages)


@pytest.mark.asyncio
async def test_shutdown_recovers_task_cancelled_before_first_execution(rbac_client):
    from aiops.models import AIOpsChatMessage
    from aiops.services.chat_jobs import WORKER_TAG
    client, headers, app = rbac_client
    created = await client.post(ROOT, headers=headers, json={})
    identifier = created.json()['id']
    async with app.state.session_factory() as database:
        message = AIOpsChatMessage(session_id=identifier, role='assistant', content='pending', metadata_data={'worker_tag': WORKER_TAG, 'processing_status': 'pending'})
        database.add(message)
        await database.commit()
        assistant_id = message.id
    jobs = app.state.chat_jobs
    jobs.reserve()
    jobs.start(identifier, 999, assistant_id, 999)
    await jobs.close()
    messages = (await client.get(ROOT + str(identifier) + '/messages/', headers=headers)).json()
    assert messages[-1]['metadata']['processing_status'] == 'failed'
    assert jobs.pending == 0 and not jobs.tasks and not jobs.tails


@pytest.mark.asyncio
async def test_deleting_session_cancels_synchronous_request_with_not_found(rbac_client, monkeypatch):
    from aiops.services import model_client
    client, headers, app = rbac_client
    await configure(client, headers, monkeypatch)
    entered = asyncio.Event()
    async def reply(*args):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(model_client, 'request_text', reply)
    created = await client.post(ROOT, headers=headers, json={})
    path = ROOT + str(created.json()['id']) + '/'
    pending = asyncio.create_task(client.post(path + 'send_message/', headers=headers, json={'content': 'hello'}))
    await asyncio.wait_for(entered.wait(), 2)
    assert (await client.delete(path, headers=headers)).status_code == 204
    response = await asyncio.wait_for(pending, 2)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_after_commit_never_leaves_unmanaged_pending_message(rbac_client, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    from starlette.requests import Request
    from sqlalchemy import select
    from rbac.models import User
    from aiops.schemas.chat import ChatInput
    from aiops.api.chat import submit_message
    client, headers, app = rbac_client
    created = await client.post(ROOT, headers=headers, json={})
    path = ROOT + str(created.json()['id']) + '/'
    committed, release = asyncio.Event(), asyncio.Event()
    original = AsyncSession.commit
    first = True
    async def delayed(database):
        nonlocal first
        delay, first = first, False
        await original(database)
        if delay:
            committed.set()
            await release.wait()
    monkeypatch.setattr(AsyncSession, 'commit', delayed)
    request = Request({'type': 'http', 'method': 'POST', 'path': path + 'send_message_async/', 'query_string': b'', 'headers': [], 'app': app, 'server': ('test', 80), 'client': ('test', 1), 'scheme': 'http'})
    request.state.correlation_id = 'cancel-test'
    async with app.state.session_factory() as database:
        actor = await database.scalar(select(User).where(User.username == 'admin'))
        pending = asyncio.create_task(submit_message(created.json()['id'], ChatInput(content='hello'), request, database, actor, False))
        await asyncio.wait_for(committed.wait(), 2)
        pending.cancel()
        release.set()
        await asyncio.gather(pending, return_exceptions=True)
    await app.state.chat_jobs.wait_all()
    messages = (await client.get(path + 'messages/', headers=headers)).json()
    assert len(messages) == 2
    assert messages[-1]['metadata']['processing_status'] == 'failed'
    assert app.state.chat_jobs.pending == 0
