import json

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select

from aidevops.database import Base
from ops.models import Alert, AlertAggregationRule, AlertIntegration, AlertNotificationChannel, AlertNotificationLog, AlertNotificationRule, AlertRecipient, AlertRecipientGroup
from eventwall.models import EventRecord
from rbac.models import User
from rbac.services.accounts import issue_token
from tests_fastapi.integration.test_rbac_reads import rbac_client


CASES = {
    'alert-integrations': {'name': 'prometheus-main', 'provider': 'prometheus', 'default_labels': {'team': 'ops'}, 'is_enabled': True, 'description': 'source'},
    'alert-recipients': {'name': 'operator', 'phone': '13800138000', 'email': 'operator@example.com', 'dingtalk_user_id': 'ding', 'feishu_user_id': 'fei', 'wecom_user_id': 'wx', 'is_enabled': True, 'description': 'recipient'},
    'alert-recipient-groups': {'name': 'on-call', 'recipient_ids': [], 'user_ids': [], 'is_enabled': True, 'description': 'group'},
    'alert-notification-channels': {'name': 'email-main', 'channel_type': 'email', 'is_enabled': True, 'send_resolved': True, 'timeout_seconds': 8, 'config': {'to': ['ops@example.com']}, 'template_title': '告警 {title}', 'template_body': '{message}'},
    'alert-notification-rules': {'name': 'notify-critical', 'matchers': [{'key': 'environment', 'op': '==', 'value': 'prod'}], 'min_level': 'critical', 'aggregation_rule': None, 'escalation_policy': None, 'channel_ids': [], 'recipient_ids': [], 'recipient_group_ids': [], 'notify_on_fire': True, 'notify_on_resolved': True, 'notify_on_escalation': True, 'is_enabled': True, 'description': 'notify'},
    'alert-aggregation-rules': {'name': 'aggregate-service', 'matchers': [], 'group_by': ['service'], 'window_minutes': 5, 'repeat_interval_minutes': 30, 'is_enabled': True, 'description': 'aggregate'},
    'alert-inhibition-rules': {'name': 'inhibit-warning', 'source_matchers': [], 'target_matchers': [], 'equal_labels': ['service'], 'duration_minutes': 60, 'is_enabled': True, 'description': 'inhibit'},
    'alert-mute-rules': {'name': 'maintenance', 'matchers': [], 'starts_at': '2026-09-15T01:00:00Z', 'ends_at': '2026-09-15T02:00:00Z', 'reason': 'deploy', 'is_enabled': True, 'description': 'mute'},
    'alert-escalation-policies': {'name': 'escalate', 'matchers': [], 'levels': [{'name': '一级', 'after_minutes': 30, 'channel_ids': []}], 'repeat_interval_minutes': 30, 'is_enabled': True, 'description': 'escalation'},
}


async def create(client, headers, kind, **changes):
    body = {**CASES[kind], **changes}
    response = await client.post('/api/' + kind + '/', headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', list(CASES))
async def test_alert_configuration_crud_and_frontend_round_trip(rbac_client, kind):
    client, headers, _ = rbac_client
    changes = {}
    if kind == 'alert-notification-rules':
        channel = await create(client, headers, 'alert-notification-channels')
        changes['channel_ids'] = [channel['id']]
    row = await create(client, headers, kind, **changes)
    root = '/api/' + kind + '/'
    page = (await client.get(root, headers=headers)).json()
    assert set(page) == {'count', 'next', 'previous', 'results'} and page['count'] == 1
    assert (await client.get(root + str(row['id']) + '/', headers=headers)).json()['id'] == row['id']
    update = {**row, 'name': row['name'] + '-put'}
    if kind == 'alert-integrations':
        update['default_label_rows'] = []
    if kind == 'alert-notification-channels':
        update.update(webhook_url='', access_token='', to='ops@example.com')
    if kind == 'alert-notification-rules':
        update['channel_ids'] = [item['id'] for item in row['channels']]
        update['recipient_ids'] = [item['id'] for item in row['recipients']]
        update['recipient_group_ids'] = [item['id'] for item in row['recipient_groups']]
    if kind == 'alert-mute-rules':
        update['range'] = [row['starts_at'], row['ends_at']]
    response = await client.put(root + str(row['id']) + '/', headers=headers, json=update)
    assert response.status_code == 200, response.text
    patch = {'template_title': 'patched'} if kind == 'alert-notification-channels' else {'description': 'patched'}
    response = await client.patch(root + str(row['id']) + '/', headers=headers, json=patch)
    assert response.status_code == 200 and response.json()['name'].endswith('-put')
    assert (await client.delete(root + str(row['id']) + '/', headers=headers)).status_code == 204
    assert (await client.get(root + str(row['id']) + '/', headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_alert_config_associations_replace_preserve_clear_and_project(rbac_client):
    client, headers, app = rbac_client
    recipient = await create(client, headers, 'alert-recipients')
    channel = await create(client, headers, 'alert-notification-channels')
    aggregation = await create(client, headers, 'alert-aggregation-rules')
    escalation = await create(client, headers, 'alert-escalation-policies', levels=[{'name': '一级', 'after_minutes': 0, 'channel_ids': [channel['id']]}])
    async with app.state.session_factory() as database:
        admin = await database.scalar(select(User).where(User.username == 'admin'))
        admin_id = admin.id
    group = await create(client, headers, 'alert-recipient-groups', recipient_ids=[recipient['id']], user_ids=[admin_id])
    assert group['recipients'][0]['id'] == recipient['id'] and group['users'][0]['id'] == admin_id
    assert {'email', 'first_name', 'last_name', 'display_name'} <= set(group['users'][0])
    kept_group = (await client.patch('/api/alert-recipient-groups/' + str(group['id']) + '/', headers=headers, json={'description': 'kept'})).json()
    assert kept_group['recipients'][0]['id'] == recipient['id'] and kept_group['users'][0]['id'] == admin_id
    cleared_group = (await client.patch('/api/alert-recipient-groups/' + str(group['id']) + '/', headers=headers, json={'recipient_ids': [], 'user_ids': []})).json()
    assert cleared_group['recipients'] == cleared_group['users'] == []
    rule = await create(client, headers, 'alert-notification-rules', channel_ids=[channel['id']], recipient_ids=[recipient['id']], recipient_group_ids=[group['id']], aggregation_rule=aggregation['id'], escalation_policy=escalation['id'])
    assert rule['channels'][0]['id'] == channel['id'] and rule['aggregation_rule_name'] == aggregation['name']
    path = '/api/alert-notification-rules/' + str(rule['id']) + '/'
    assert len((await client.patch(path, headers=headers, json={'description': 'keep'})).json()['channels']) == 1
    assert (await client.patch(path, headers=headers, json={'is_enabled': False, 'channel_ids': []})).status_code == 400
    cleared = (await client.patch(path, headers=headers, json={'recipient_ids': [], 'recipient_group_ids': []})).json()
    assert len(cleared['channels']) == 1 and cleared['recipients'] == cleared['recipient_groups'] == []
    assert (await client.delete('/api/alert-aggregation-rules/' + str(aggregation['id']) + '/', headers=headers)).status_code == 204
    assert (await client.get(path, headers=headers)).json()['aggregation_rule'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,body', [
    ('alert-integrations', {'name': 'x', 'provider': 'bad'}),
    ('alert-recipients', {'name': 'x', 'email': 'bad'}),
    ('alert-notification-channels', {'name': 'x', 'channel_type': 'email', 'timeout_seconds': True}),
    ('alert-aggregation-rules', {'name': 'x', 'matchers': [{'key': 'token', 'op': '==', 'value': 'x'}]}),
    ('alert-inhibition-rules', {'name': 'x', 'source_matchers': [{'key': 'x', 'op': 'bad', 'value': 'x'}]}),
    ('alert-mute-rules', {'name': 'x', 'starts_at': '2026-09-15T02:00:00Z', 'ends_at': '2026-09-15T01:00:00Z'}),
    ('alert-escalation-policies', {'name': 'x', 'levels': []}),
    ('alert-notification-rules', {'name': 'x', 'channel_ids': []}),
])
async def test_alert_config_validation_boundaries(rbac_client, kind, body):
    client, headers, _ = rbac_client
    assert (await client.post('/api/' + kind + '/', headers=headers, json=body)).status_code in (400, 422)


@pytest.mark.asyncio
async def test_alert_config_rejects_missing_relationship_ids(rbac_client):
    client, headers, _ = rbac_client
    assert (await client.post('/api/alert-recipient-groups/', headers=headers, json={'name': 'x', 'recipient_ids': [999], 'user_ids': [999]})).status_code == 400
    assert (await client.post('/api/alert-notification-rules/', headers=headers, json={'name': 'x', 'channel_ids': [999]})).status_code == 400
    assert (await client.post('/api/alert-escalation-policies/', headers=headers, json={'name': 'x', 'levels': [{'name': 'x', 'after_minutes': 0, 'channel_ids': [999]}]})).status_code == 400


@pytest.mark.asyncio
async def test_integration_token_is_server_generated_and_not_writable(rbac_client):
    client, headers, app = rbac_client
    row = await create(client, headers, 'alert-integrations')
    assert row['webhook_url'].startswith('/api/alerts/webhooks/prometheus/') and 'token' not in row and 'secret' not in row
    assert (await client.post('/api/alert-integrations/', headers=headers, json={**CASES['alert-integrations'], 'token': 'chosen'})).status_code == 422
    async with app.state.session_factory() as database:
        stored = await database.get(AlertIntegration, row['id'])
        assert len(stored.token) >= 40 and stored.token in row['webhook_url']


@pytest.mark.asyncio
async def test_channel_secrets_are_encrypted_masked_preserved_and_cleared(rbac_client, monkeypatch):
    client, headers, app = rbac_client
    monkeypatch.setenv('AIOPS_CONFIG_ENCRYPTION_KEY', Fernet.generate_key().decode())
    row = await create(client, headers, 'alert-notification-channels', config={'webhook_url': 'https://example.com/private', 'access_token': 'private-token', 'to': ['ops@example.com']})
    assert row['config'] == {'webhook_url': '***', 'access_token': '***', 'to': ['ops@example.com']}
    async with app.state.session_factory() as database:
        stored = await database.get(AlertNotificationChannel, row['id'])
        serialized = json.dumps(stored.config)
        assert 'private-token' not in serialized and '__aiops_secret_v1__' in serialized
    path = '/api/alert-notification-channels/' + str(row['id']) + '/'
    kept = (await client.put(path, headers=headers, json={**row, 'webhook_url': '***', 'access_token': '***', 'to': 'ops@example.com'})).json()
    assert kept['config']['access_token'] == '***'
    cleared = (await client.patch(path, headers=headers, json={'config': {'webhook_url': '', 'access_token': '', 'to': []}})).json()
    assert cleared['config']['access_token'] == '' and cleared['config']['webhook_url'] == ''


@pytest.mark.asyncio
async def test_channel_legacy_plaintext_is_only_masked_on_read(rbac_client, memory_session):
    client, headers, _ = rbac_client
    item = AlertNotificationChannel(name='legacy', channel_type='dingtalk', config={'webhook_url': 'https://example.com/legacy', 'access_token': 'legacy-secret'})
    memory_session.add(item)
    await memory_session.commit()
    response = await client.get('/api/alert-notification-channels/' + str(item.id) + '/', headers=headers)
    assert response.status_code == 200 and 'legacy-secret' not in response.text and 'example.com/legacy' not in response.text
    await memory_session.refresh(item)
    assert item.config['access_token'] == 'legacy-secret'


@pytest.mark.asyncio
async def test_channel_secret_requires_key_and_new_path_rejects_mask(rbac_client, monkeypatch):
    client, headers, _ = rbac_client
    monkeypatch.setenv('AIOPS_CONFIG_ENCRYPTION_KEY', 'invalid-key')
    response = await client.post('/api/alert-notification-channels/', headers=headers, json={**CASES['alert-notification-channels'], 'config': {'access_token': 'private'}})
    assert response.status_code == 503
    monkeypatch.setenv('AIOPS_CONFIG_ENCRYPTION_KEY', Fernet.generate_key().decode())
    response = await client.post('/api/alert-notification-channels/', headers=headers, json={**CASES['alert-notification-channels'], 'config': {'access_token': '***'}})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_matchers_follow_frontend_operator_and_size_contract(rbac_client):
    client, headers, _ = rbac_client
    matchers = [
        {'key': 'service', 'op': 'not in', 'value': [str(index) for index in range(100)]},
        {'key': 'message', 'op': 'contains', 'value': 'x' * 1200},
    ]
    assert (await client.post('/api/alert-aggregation-rules/', headers=headers, json={'name': 'frontend-matchers', 'matchers': matchers})).status_code == 201


@pytest.mark.asyncio
async def test_resource_specific_roundtrip_fields_and_whitespace_time_validation(rbac_client):
    client, headers, _ = rbac_client
    assert (await client.post('/api/alert-recipients/', headers=headers, json={'name': 'x', 'webhook_url': 'ignored?'})).status_code == 422
    assert (await client.post('/api/alert-aggregation-rules/', headers=headers, json={'name': 'x', 'group_by': ['   ']})).status_code == 422
    assert (await client.post('/api/alert-aggregation-rules/', headers=headers, json={'name': 'x', 'group_by': None})).status_code == 422
    assert (await client.post('/api/alert-inhibition-rules/', headers=headers, json={'name': 'x', 'equal_labels': 'service'})).status_code == 422
    assert (await client.post('/api/alert-escalation-policies/', headers=headers, json={'name': 'x', 'levels': [{'name': '  ', 'after_minutes': 0, 'channel_ids': []}]})).status_code == 422
    response = await client.post('/api/alert-mute-rules/', headers=headers, json={'name': 'x', 'starts_at': '2026-09-15T01:00:00', 'ends_at': '2026-09-15T02:00:00Z'})
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_manage_only_response_does_not_disclose_integration_token(rbac_client, memory_session):
    from rbac.models import PermissionDefinition, Role
    client, _, _ = rbac_client
    permission = await memory_session.scalar(select(PermissionDefinition).where(PermissionDefinition.code == 'ops.alert.config.manage'))
    role = Role(name='config-manager-only', code='config-manager-only', permissions=[permission])
    user = User(username='config-manager-only', password_hash='unused', roles=[role])
    memory_session.add(user)
    await memory_session.flush()
    token = await issue_token(memory_session, user)
    await memory_session.commit()
    response = await client.post('/api/alert-integrations/', headers={'Authorization': 'Token ' + token}, json=CASES['alert-integrations'])
    assert response.status_code == 201 and 'webhook_url' not in response.json() and 'token' not in response.text


@pytest.mark.asyncio
async def test_channel_delete_rejects_live_rule_and_escalation_references(rbac_client):
    client, headers, _ = rbac_client
    channel = await create(client, headers, 'alert-notification-channels')
    await create(client, headers, 'alert-notification-rules', channel_ids=[channel['id']])
    assert (await client.delete('/api/alert-notification-channels/' + str(channel['id']) + '/', headers=headers)).status_code == 409
    second = await create(client, headers, 'alert-notification-channels', name='second')
    await create(client, headers, 'alert-escalation-policies', name='policy-second', levels=[{'name': 'x', 'after_minutes': 0, 'channel_ids': [second['id']]}])
    assert (await client.delete('/api/alert-notification-channels/' + str(second['id']) + '/', headers=headers)).status_code == 409


@pytest.mark.asyncio
async def test_alert_config_pagination_search_unique_conflict_and_audit(rbac_client, memory_session):
    client, headers, _ = rbac_client
    for index in range(21):
        await create(client, headers, 'alert-recipient-groups', name=f'group-{index:02d}', description='needle' if index == 7 else '')
    page = (await client.get('/api/alert-recipient-groups/?page=2', headers=headers)).json()
    assert page['count'] == 21 and len(page['results']) == 1 and page['previous'] and page['next'] is None
    searched = (await client.get('/api/alert-recipient-groups/?search=needle', headers=headers)).json()
    assert searched['count'] == 1 and searched['results'][0]['name'] == 'group-07'
    await create(client, headers, 'alert-mute-rules', name='maintenance-search', reason='deploy-window')
    assert (await client.get('/api/alert-mute-rules/?search=deploy-window', headers=headers)).json()['count'] == 1
    assert (await client.post('/api/alert-recipient-groups/', headers=headers, json={'name': 'group-00'})).status_code == 409
    event = await memory_session.scalar(select(EventRecord).where(EventRecord.resource_type == 'alert_recipient_group').order_by(EventRecord.id.desc()))
    assert event is not None and event.event_metadata == {'fields': ['description', 'is_enabled', 'name', 'recipient_ids', 'user_ids']}


@pytest.mark.asyncio
async def test_group_associations_roll_back_when_commit_fails(rbac_client, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    client, headers, app = rbac_client
    recipient = await create(client, headers, 'alert-recipients')
    async def fail(*args, **kwargs):
        raise RuntimeError('simulated failure')
    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, 'commit', fail)
        response = await client.post('/api/alert-recipient-groups/', headers=headers, json={'name': 'rollback-group', 'recipient_ids': [recipient['id']], 'user_ids': []})
    assert response.status_code == 500
    async with app.state.session_factory() as database:
        assert await database.scalar(select(func.count()).select_from(AlertRecipientGroup).where(AlertRecipientGroup.name == 'rollback-group')) == 0


@pytest.mark.asyncio
async def test_notification_log_read_is_filtered_and_safe(rbac_client, memory_session):
    client, headers, _ = rbac_client
    alert = Alert(title='x', source='x', message='x')
    channel = AlertNotificationChannel(name='email', channel_type='email')
    rule = AlertNotificationRule(name='rule')
    memory_session.add_all([alert, channel, rule])
    await memory_session.flush()
    log = AlertNotificationLog(alert_id=alert.id, channel_id=channel.id, rule_id=rule.id, action='fire', status='error', recipient_summary='ops', request_payload={'token': 'secret'}, response_body='secret', error_message='secret')
    memory_session.add(log)
    await memory_session.commit()
    response = await client.get('/api/alert-notification-logs/?status=error&alert=' + str(alert.id), headers=headers)
    assert response.status_code == 200 and response.json()['count'] == 1
    result = response.json()['results'][0]
    assert result['channel_name'] == 'email' and result['channel_type'] == 'email'
    assert result['request_payload'] == {} and result['response_body'] == ''
    assert 'secret' not in response.text


@pytest.mark.asyncio
async def test_alert_config_permissions(rbac_client, memory_session):
    from rbac.models import PermissionDefinition, Role
    client, headers, _ = rbac_client
    permission = await memory_session.scalar(select(PermissionDefinition).where(PermissionDefinition.code == 'ops.alert.config.view'))
    role = Role(name='config-reader', code='config-reader', permissions=[permission])
    user = User(username='config-reader', password_hash='unused', roles=[role])
    memory_session.add(user)
    await memory_session.flush()
    token = await issue_token(memory_session, user)
    await memory_session.commit()
    viewer = {'Authorization': 'Token ' + token}
    assert (await client.get('/api/alert-integrations/')).status_code == 401
    assert (await client.get('/api/alert-integrations/', headers=viewer)).status_code == 200
    assert (await client.post('/api/alert-integrations/', headers=viewer, json=CASES['alert-integrations'])).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['audit', 'commit'])
async def test_alert_config_transaction_failure_rolls_back(rbac_client, monkeypatch, failure):
    from sqlalchemy.ext.asyncio import AsyncSession
    from ops.alerts import config_services as alert_config
    client, headers, app = rbac_client
    async def fail(*args, **kwargs):
        raise RuntimeError('simulated failure')
    with monkeypatch.context() as patch:
        patch.setattr(alert_config if failure == 'audit' else AsyncSession, 'record_event' if failure == 'audit' else 'commit', fail)
        response = await client.post('/api/alert-recipients/', headers=headers, json=CASES['alert-recipients'])
    assert response.status_code == 500
    async with app.state.session_factory() as database:
        assert await database.scalar(select(func.count()).select_from(AlertRecipient)) == 0
        assert await database.scalar(select(func.count()).select_from(EventRecord).where(EventRecord.resource_type == 'alert_recipient')) == 0


@pytest.mark.asyncio
async def test_configuration_delete_preserves_business_rows(rbac_client, memory_session):
    client, headers, _ = rbac_client
    integration = await create(client, headers, 'alert-integrations')
    channel = await create(client, headers, 'alert-notification-channels')
    alert = Alert(title='x', source='x', message='x', integration_id=integration['id'])
    memory_session.add(alert)
    await memory_session.flush()
    log = AlertNotificationLog(alert_id=alert.id, channel_id=channel['id'])
    memory_session.add(log)
    await memory_session.commit()
    assert (await client.delete('/api/alert-integrations/' + str(integration['id']) + '/', headers=headers)).status_code == 204
    assert (await client.delete('/api/alert-notification-channels/' + str(channel['id']) + '/', headers=headers)).status_code == 204
    await memory_session.refresh(alert)
    await memory_session.refresh(log)
    assert alert.integration_id is None and log.channel_id is None
