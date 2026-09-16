import pytest
from sqlalchemy import select, func

from tests_fastapi.integration.test_rbac_reads import rbac_client
from ops.models import Alert, AlertClaim, AlertAction
from eventwall.models import EventRecord
from rbac.models import User
from rbac.services.accounts import issue_token


ROOT = '/api/alerts/'


async def create(client, headers, **values):
    data = {'title': 'CPU告警', 'source': 'monitor', 'message': 'CPU high', 'level': 'critical', 'environment': 'prod', 'service': 'api'}
    data.update(values)
    response = await client.post(ROOT, headers=headers, json=data)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_alert_list_summary_groups_detail_contract(rbac_client):
    client, headers, _ = rbac_client
    row = await create(client, headers)
    await create(client, headers, title='内存告警', level='warning', environment='test')
    result = (await client.get(ROOT, headers=headers)).json()
    assert result['count'] == 2 and set(result) == {'count', 'next', 'previous', 'results'}
    assert result['results'][0]['title'] == '内存告警'
    detail = (await client.get(ROOT + str(row['id']) + '/', headers=headers)).json()
    assert detail['level_display'] == '严重' and detail['status_display'] == '活跃'
    assert detail['claimants'] == [] and detail['current_user_claimed'] is False
    assert detail['actions'] == [] and detail['recent_notifications'] == []
    summary = (await client.get(ROOT + 'summary/?page=99', headers=headers)).json()
    assert summary['total'] == 2 and summary['unacknowledged'] == 2
    groups = (await client.get(ROOT + 'groups/?group_by=environment', headers=headers)).json()
    assert len(groups) == 2 and groups[0]['total'] == 1 and groups[0]['sample_alert_id'] == row['id']


@pytest.mark.asyncio
@pytest.mark.parametrize('query', ['environment=prod', 'level=critical', 'search=CPU', 'resource=server', 'label_key=team&label_value=ops', 'source_type=prometheus', 'system=finance'])
async def test_alert_filters_share_summary_and_list(rbac_client, query):
    client, headers, _ = rbac_client
    await create(client, headers, resource='server-1', labels={'team': 'ops'}, source_type='prometheus', business_line='finance')
    await create(client, headers, title='other', message='other message', level='info', environment='test', resource='other', service='other', source_type='generic')
    page = (await client.get(ROOT + '?' + query, headers=headers)).json()
    summary = (await client.get(ROOT + 'summary/?' + query, headers=headers)).json()
    assert page['count'] == summary['total'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('action', ['acknowledge', 'claim', 'unclaim', 'mute', 'resolve', 'close', 'reopen'])
async def test_alert_state_actions_and_audit(rbac_client, action):
    client, headers, app = rbac_client
    row = await create(client, headers)
    path = ROOT + str(row['id']) + '/'
    response = await client.post(path + action + '/', headers=headers, json={'note': '人工处理'})
    assert response.status_code == 200
    state = response.json()
    if action == 'acknowledge':
        assert state['is_acknowledged'] and not state['claimants']
    if action == 'claim':
        assert state['current_user_claimed'] and state['claimed_by'] == 'admin'
    if action == 'mute':
        assert state['status'] == 'muted' and state['is_suppressed'] and state['mute_until']
    if action in ['resolve', 'close', 'reopen']:
        assert state['status'] == {'resolve': 'resolved', 'close': 'closed', 'reopen': 'active'}[action]
    assert state['actions'][0]['action'] == action and state['actions'][0]['actor'] == 'admin'
    async with app.state.session_factory() as database:
        assert await database.scalar(select(func.count()).select_from(EventRecord).where(EventRecord.action == action)) == 1


@pytest.mark.asyncio
async def test_alert_claim_is_idempotent_and_unclaim_only_own_claim(rbac_client, memory_session):
    client, headers, _ = rbac_client
    row = await create(client, headers)
    path = ROOT + str(row['id']) + '/'
    memory_session.add(User(username='operator', password_hash='unused', is_superuser=True))
    await memory_session.flush()
    other = await memory_session.scalar(select(User).where(User.username == 'operator'))
    token = await issue_token(memory_session, other)
    await memory_session.commit()
    other_headers = {'Authorization': 'Token ' + token}
    for actor in [headers, headers, other_headers]:
        assert (await client.post(path + 'claim/', headers=actor, json={})).status_code == 200
    state = (await client.get(path, headers=headers)).json()
    assert state['claimant_count'] == 2 and state['claimed_by'] == 'admin、operator'
    state = (await client.post(path + 'unclaim/', headers=headers, json={})).json()
    assert state['claimed_by'] == 'operator' and not state['current_user_claimed']
    assert (await client.get(ROOT + '?claimed=1', headers=headers)).json()['count'] == 1
    assert (await client.get(ROOT + '?ack=0', headers=headers)).json()['count'] == 0


@pytest.mark.asyncio
async def test_alert_crud_patch_preserves_fields_delete_cascades(rbac_client):
    client, headers, app = rbac_client
    row = await create(client, headers)
    path = ROOT + str(row['id']) + '/'
    await client.post(path + 'claim/', headers=headers, json={})
    response = await client.patch(path, headers=headers, json={'title': 'new'})
    assert response.status_code == 200 and response.json()['message'] == 'CPU high'
    assert (await client.put(path, headers=headers, json={'title': 'put', 'source': 'new', 'message': 'put'})).status_code == 200
    assert (await client.get('/api/alert-actions/?alert=' + str(row['id']), headers=headers)).json()['count'] == 1
    assert (await client.delete(path, headers=headers)).status_code == 204
    assert (await client.get(path, headers=headers)).status_code == 404
    async with app.state.session_factory() as database:
        for model in [AlertClaim, AlertAction]:
            assert await database.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [{'minutes': 0}, {'minutes': 10081}, {'minutes': True}, {'minutes': 1.5}, {'actor': 'hacker'}])
async def test_alert_invalid_action_inputs_rejected(rbac_client, body):
    client, headers, _ = rbac_client
    row = await create(client, headers)
    assert (await client.post(ROOT + str(row['id']) + '/mute/', headers=headers, json=body)).status_code == 422


@pytest.mark.asyncio
async def test_alert_authentication_permission_missing_and_readonly_fields(rbac_client, memory_session):
    client, headers, _ = rbac_client
    assert (await client.get(ROOT)).status_code == 401
    user = User(username='unprivileged', password_hash='unused')
    memory_session.add(user)
    await memory_session.flush()
    token = await issue_token(memory_session, user)
    await memory_session.commit()
    assert (await client.get(ROOT, headers={'Authorization': 'Token ' + token})).status_code == 403
    assert (await client.get(ROOT + '999/', headers=headers)).status_code == 404
    assert (await client.post(ROOT, headers=headers, json={'title': 'x', 'source': 'x', 'message': 'x', 'claimed_by': 'hacker'})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['audit', 'commit'])
async def test_alert_action_transaction_failure_rolls_back_state_and_records(rbac_client, monkeypatch, failure):
    from sqlalchemy.ext.asyncio import AsyncSession
    from eventwall import services as events
    client, headers, app = rbac_client
    row = await create(client, headers)
    async def fail(*args, **kwargs):
        raise RuntimeError('simulated failure')
    with monkeypatch.context() as patch:
        patch.setattr(events if failure == 'audit' else AsyncSession, 'record_event' if failure == 'audit' else 'commit', fail)
        response = await client.post(ROOT + str(row['id']) + '/claim/', headers=headers, json={})
    assert response.status_code == 500
    async with app.state.session_factory() as database:
        assert await database.scalar(select(func.count()).select_from(AlertClaim)) == 0
        assert await database.scalar(select(func.count()).select_from(AlertAction)) == 0
        assert (await database.get(Alert, row['id'])).claimed_by == ''


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [{'title': 'x' * 257}, {'level': 'invalid'}, {'host': 0}, {'environment': 'x' * 65}, {'status': 'closed'}, {'labels': None}])
async def test_alert_patch_retains_create_validation(rbac_client, payload):
    client, headers, _ = rbac_client
    row = await create(client, headers)
    assert (await client.patch(ROOT + str(row['id']) + '/', headers=headers, json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_alert_system_name_alias_and_resource_claim_combination(rbac_client):
    client, headers, _ = rbac_client
    row = await create(client, headers, business_line='finance', resource='server-1')
    await create(client, headers, business_line='other', resource='server-2')
    await client.post(ROOT + str(row['id']) + '/claim/', headers=headers, json={})
    response = await client.get(ROOT + '?resource=server&claimed=1&system_name=finance', headers=headers)
    assert response.status_code == 200 and response.json()['count'] == 1
    assert (await client.get(ROOT + '?system_name=missing', headers=headers)).json()['count'] == 0


@pytest.mark.asyncio
async def test_alert_group_sensitive_label_does_not_expose_secret(rbac_client):
    client, headers, _ = rbac_client
    await create(client, headers, labels={'api_key': 'private-token'})
    response = await client.get(ROOT + 'groups/?group_by=label.api_key', headers=headers)
    assert response.status_code == 422 and 'private-token' not in response.text


@pytest.mark.asyncio
async def test_alert_group_nested_label_is_sanitized_before_string_conversion(rbac_client):
    client, headers, _ = rbac_client
    await create(client, headers, labels={'team': {'token': 'private-token', 'name': 'ops'}})
    response = await client.get(ROOT + 'groups/?group_by=label.team', headers=headers)
    assert response.status_code == 200 and 'private-token' not in response.text and 'ops' in response.text


@pytest.mark.asyncio
async def test_alert_reopen_preserves_claimants_and_legacy_history(rbac_client):
    client, headers, _ = rbac_client
    row = await create(client, headers)
    path = ROOT + str(row['id']) + '/'
    for action in ['claim', 'acknowledge', 'mute', 'resolve', 'close', 'reopen']:
        assert (await client.post(path + action + '/', headers=headers, json={})).status_code == 200
    state = (await client.get(path, headers=headers)).json()
    assert state['status'] == 'active' and not state['is_acknowledged'] and not state['is_suppressed']
    assert state['closed_at'] is None and state['ends_at'] is None
    assert state['claimant_count'] == 1 and state['mute_until'] is not None


@pytest.mark.asyncio
async def test_alert_pagination_count_and_summary_are_independent(rbac_client, memory_session):
    client, headers, _ = rbac_client
    memory_session.add_all([Alert(title='row' + str(index), source='test', message='message') for index in range(21)])
    await memory_session.commit()
    first = (await client.get(ROOT, headers=headers)).json()
    second = (await client.get(first['next'], headers=headers)).json()
    assert first['count'] == second['count'] == 21 and len(first['results']) == 20 and len(second['results']) == 1
    assert second['previous'] and second['next'] is None
    assert (await client.get(ROOT + 'summary/?page=2', headers=headers)).json()['total'] == 21


@pytest.mark.asyncio
async def test_alert_existing_notifications_are_safe_and_limited(rbac_client, memory_session):
    from ops.models import AlertNotificationLog
    client, headers, _ = rbac_client
    row = await create(client, headers, raw_payload={'authorization': 'private-token'})
    memory_session.add_all([AlertNotificationLog(alert_id=row['id'], status='error', response_body='private-token', error_message='private-token', request_payload={'token': 'private-token'}) for _ in range(7)])
    await memory_session.commit()
    response = await client.get(ROOT + str(row['id']) + '/', headers=headers)
    assert response.status_code == 200 and 'private-token' not in response.text
    assert len(response.json()['recent_notifications']) == 5


@pytest.mark.asyncio
async def test_alert_view_only_account_can_read_but_cannot_write(rbac_client, memory_session):
    from rbac.models import PermissionDefinition, Role
    client, headers, _ = rbac_client
    row = await create(client, headers)
    permission = await memory_session.scalar(select(PermissionDefinition).where(PermissionDefinition.code == 'ops.alert.view'))
    role = Role(name='alert-reader', code='alert-reader', permissions=[permission])
    user = User(username='alert-reader', password_hash='unused', roles=[role])
    memory_session.add(user)
    await memory_session.flush()
    token = await issue_token(memory_session, user)
    await memory_session.commit()
    viewer = {'Authorization': 'Token ' + token}
    path = ROOT + str(row['id']) + '/'
    for url in [ROOT, path, ROOT + 'summary/', ROOT + 'groups/', '/api/alert-actions/']:
        assert (await client.get(url, headers=viewer)).status_code == 200
    for action in ['claim', 'unclaim', 'mute', 'acknowledge', 'resolve', 'close', 'reopen']:
        assert (await client.post(path + action + '/', headers=viewer, json={})).status_code == 403
    assert (await client.patch(path, headers=viewer, json={'title': 'hack'})).status_code == 403
    assert (await client.delete(path, headers=viewer)).status_code == 403


@pytest.mark.asyncio
async def test_alert_claim_queries_use_current_reads_for_mysql_repeatable_read(rbac_client, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.selectable import Select
    client, headers, _ = rbac_client
    row = await create(client, headers)
    captured = []
    # 仅观察真实SQL表达式，不替换查询结果，SQLite仍执行完整业务事务。
    original_scalar, original_scalars = AsyncSession.scalar, AsyncSession.scalars
    async def scalar(self, statement, *args, **kwargs):
        if isinstance(statement, Select) and any(getattr(table, 'name', '') == 'ops_alertclaim' for table in statement.get_final_froms()):
            captured.append(statement)
        return await original_scalar(self, statement, *args, **kwargs)
    async def scalars(self, statement, *args, **kwargs):
        if isinstance(statement, Select) and any(getattr(table, 'name', '') == 'ops_alertclaim' for table in statement.get_final_froms()):
            captured.append(statement)
        return await original_scalars(self, statement, *args, **kwargs)
    monkeypatch.setattr(AsyncSession, 'scalar', scalar)
    monkeypatch.setattr(AsyncSession, 'scalars', scalars)
    response = await client.post(ROOT + str(row['id']) + '/claim/', headers=headers, json={})
    assert response.status_code == 200 and len(captured) >= 3
    assert all(statement._for_update_arg is not None for statement in captured)
