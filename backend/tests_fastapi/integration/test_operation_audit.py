from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from eventwall.models import EventRecord
from rbac.models import User
from rbac.services.accounts import issue_token
from test_rbac_reads import rbac_client


LIST = '/api/events/operation_audit/'
PRUNE = '/api/events/prune_operation_audit/'
NOW = datetime(2025, 1, 2, tzinfo=timezone.utc)


async def seed(session, **values):
    event = EventRecord(module='rbac', category='system', action='update_user', title='修改用户', occurred_at=NOW, **values)
    session.add(event)
    await session.flush()
    return event


@pytest.mark.asyncio
async def test_query_scope_shape_labels_and_order(rbac_client, memory_session):
    client, headers, _ = rbac_client
    first = await seed(memory_session, actor_username='admin', resource_name='中文资源', detail='secret-content', event_metadata={'password': 'secret'})
    second = await seed(memory_session, source_type='async', result='failed')
    await seed(memory_session, source_type='external')
    memory_session.add(EventRecord(module='ops', category='external_event', action='ingest', title='外部'))
    await seed(memory_session, result='rejected')
    await memory_session.commit()
    response = await client.get(LIST, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == {'count', 'next', 'previous', 'results'}
    assert data['count'] == 2 and [r['id'] for r in data['results']] == [second.id, first.id]
    assert data['results'][0]['result_display'] == '失败'
    assert data['results'][0]['source_type_display'] == '异步任务'
    assert 'secret' not in response.text and 'metadata' not in response.text
    assert data['results'][0]['occurred_at'].endswith(('Z', '+00:00'))


@pytest.mark.asyncio
async def test_query_combined_filters_and_utc_boundaries(rbac_client, memory_session):
    client, headers, _ = rbac_client
    matching = await seed(memory_session, actor_username='Alice', actor_display='运维', resource_name='机房%_一', result='partial')
    await seed(memory_session, actor_username='other', resource_name='机房xx一')
    await memory_session.commit()
    params = {'search': '%_', 'actor': ' Alice ', 'module': ' rbac ', 'result': 'partial', 'start_at': '2025-01-02T08:00:00+08:00', 'end_at': NOW.isoformat()}
    response = await client.get(LIST, headers=headers, params=params)
    assert response.status_code == 200, response.text
    assert [r['id'] for r in response.json()['results']] == [matching.id]
    for search in ['运维', '修改', '机房']:
        assert (await client.get(LIST, headers=headers, params={'search': search})).json()['count'] >= 1
    assert (await client.get(LIST, headers=headers, params={'result': 'rejected'})).json()['count'] == 0


@pytest.mark.asyncio
async def test_query_pagination_cap_and_empty(rbac_client, memory_session):
    client, headers, _ = rbac_client
    assert (await client.get(LIST, headers=headers)).json()['count'] == 0
    for index in range(205):
        await seed(memory_session, resource_id=str(index))
    await memory_session.commit()
    default = (await client.get(LIST, headers=headers)).json()
    assert len(default['results']) == 20 and default['previous'] is None
    assert 'page=2' in default['next']
    capped = (await client.get(LIST, headers=headers, params={'page_size': 1000})).json()
    assert len(capped['results']) == 200 and 'page_size=200' in capped['next']
    last = (await client.get(LIST, headers=headers, params={'page': 2, 'page_size': 200})).json()
    assert len(last['results']) == 5 and last['next'] is None and last['previous']
    assert (await client.get(LIST, headers=headers, params={'page': 100})).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize('params', [{'page': 0}, {'page_size': 0}, {'result': 'unknown'}, {'start_at': 'bad'}, {'start_at': '2025-01-01T00:00:00'}, {'start_at': '2025-01-03T00:00:00Z', 'end_at': '2025-01-02T00:00:00Z'}])
async def test_query_invalid_input(rbac_client, params):
    client, headers, _ = rbac_client
    assert (await client.get(LIST, headers=headers, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_query_and_prune_require_permissions(rbac_client, memory_session):
    client, _, _ = rbac_client
    user = User(username='audit-no-permission', password_hash='unused')
    memory_session.add(user)
    await memory_session.flush()
    token = await issue_token(memory_session, user)
    await memory_session.commit()
    for headers, status in [({}, 401), ({'Authorization': f'Token {token}'}, 403)]:
        assert (await client.get(LIST, headers=headers)).status_code == status
        assert (await client.post(PRUNE, headers=headers, json={'before_at': NOW.isoformat()})).status_code == status


@pytest.mark.asyncio
async def test_prune_strict_scope_preserves_child_and_logs(rbac_client, memory_session):
    client, headers, app = rbac_client
    parent = await seed(memory_session)
    child = await seed(memory_session, parent_event_id=parent.id)
    child.occurred_at = NOW + timedelta(days=2)
    boundary = await seed(memory_session)
    boundary.occurred_at = NOW + timedelta(days=1)
    external = await seed(memory_session, source_type='external')
    rejected = await seed(memory_session, result='rejected')
    external_category = EventRecord(module='ops', category='external_event', action='ingest', title='外部', occurred_at=NOW)
    memory_session.add(external_category)
    await memory_session.commit()
    cutoff = NOW + timedelta(days=1)
    response = await client.post(PRUNE, headers=headers, json={'before_at': cutoff.isoformat()})
    assert response.status_code == 200, response.text
    assert response.json()['deleted'] == 1
    async with app.state.session_factory() as session:
        rows = list((await session.scalars(select(EventRecord))).all())
        ids = {row.id for row in rows}
        assert parent.id not in ids and {child.id, boundary.id, external.id, rejected.id, external_category.id} <= ids
        assert (await session.get(EventRecord, child.id)).parent_event_id is None
        log = next(row for row in rows if row.action == 'prune_operation_audit')
        assert log.event_metadata['deleted'] == 1 and log.category == 'resource_change' and log.severity == 'warning'
        assert log.occurred_at > cutoff
    zero = await client.post(PRUNE, headers=headers, json={'before_at': NOW.isoformat()})
    assert zero.status_code == 200 and zero.json()['deleted'] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [{}, {'before_at': None}, {'before_at': 'bad'}, {'before_at': '2025-01-01T00:00:00'}, {'before_at': '2999-01-01T00:00:00Z'}, {'before_at': NOW.isoformat(), 'extra': 1}])
async def test_prune_invalid_body(rbac_client, body):
    client, headers, _ = rbac_client
    assert (await client.post(PRUNE, headers=headers, json=body)).status_code == 422


@pytest.mark.asyncio
async def test_prune_rejects_query_filters(rbac_client):
    client, headers, _ = rbac_client
    assert (await client.post(PRUNE, headers=headers, params={'module': 'rbac'}, json={'before_at': NOW.isoformat()})).status_code == 422


@pytest.mark.asyncio
async def test_prune_audit_failure_rolls_back(rbac_client, memory_session, monkeypatch):
    client, headers, app = rbac_client
    target = await seed(memory_session)
    await memory_session.commit()
    import rbac.audit.service as service

    async def fail(*args, **kwargs):
        raise RuntimeError('private-error')

    monkeypatch.setattr(service, 'record_event', fail)
    response = await client.post(PRUNE, headers=headers, json={'before_at': (NOW + timedelta(days=1)).isoformat()})
    assert response.status_code == 500 and 'private-error' not in response.text
    async with app.state.session_factory() as session:
        assert await session.get(EventRecord, target.id) is not None
        assert not list((await session.scalars(select(EventRecord).where(EventRecord.action == 'prune_operation_audit'))).all())


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [1735776000, '1735776000'])
async def test_prune_requires_iso_string_not_unix_timestamp(rbac_client, value):
    client, headers, _ = rbac_client
    assert (await client.post(PRUNE, headers=headers, json={'before_at': value})).status_code == 422


@pytest.mark.asyncio
async def test_query_rejects_unix_timestamp(rbac_client):
    client, headers, _ = rbac_client
    assert (await client.get(LIST, headers=headers, params={'start_at': '1735776000'})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize('code', ['rbac.audit.view', 'rbac.audit.manage'])
async def test_ordinary_account_receives_only_granted_audit_operation(rbac_client, memory_session, code):
    from rbac.models import PermissionDefinition, Role

    client, _, _ = rbac_client
    permission = await memory_session.scalar(select(PermissionDefinition).where(PermissionDefinition.code == code))
    role = Role(code='audit-test-role', name='审计测试角色', permissions=[permission])
    user = User(username='audit-ordinary', password_hash='unused', roles=[role])
    memory_session.add(user)
    await memory_session.flush()
    token = await issue_token(memory_session, user)
    await memory_session.commit()
    headers = {'Authorization': f'Token {token}'}
    read = await client.get(LIST, headers=headers)
    write = await client.post(PRUNE, headers=headers, json={'before_at': NOW.isoformat()})
    assert read.status_code == (200 if code == 'rbac.audit.view' else 403)
    assert write.status_code == (200 if code == 'rbac.audit.manage' else 403)


@pytest.mark.asyncio
@pytest.mark.parametrize('value', ['9999-12-31T23:59:59-01:00', '0001-01-01T00:00:00+01:00'])
async def test_timezone_overflow_returns_validation_error(rbac_client, value):
    client, headers, _ = rbac_client
    assert (await client.get(LIST, headers=headers, params={'start_at': value})).status_code == 422
    assert (await client.post(PRUNE, headers=headers, json={'before_at': value})).status_code == 422


@pytest.mark.asyncio
async def test_cleanup_log_preserves_whole_second_mysql_timestamp(rbac_client, monkeypatch):
    import rbac.audit.service as service

    client, headers, app = rbac_client
    clock = NOW + timedelta(microseconds=900000)
    cutoff = NOW + timedelta(microseconds=800000)
    monkeypatch.setattr(service, 'utc_now', lambda: clock, raising=False)
    response = await client.post(PRUNE, headers=headers, json={'before_at': cutoff.isoformat()})
    assert response.status_code == 200
    async with app.state.session_factory() as session:
        log = await session.scalar(select(EventRecord).where(EventRecord.action == 'prune_operation_audit'))
        assert log.occurred_at.microsecond == 0
        assert cutoff < log.occurred_at <= clock + timedelta(seconds=1)
    again = await client.post(PRUNE, headers=headers, json={'before_at': cutoff.isoformat()})
    assert again.json()['deleted'] == 0


@pytest.mark.asyncio
async def test_prune_commit_failure_rolls_back_deletion_and_log(rbac_client, memory_session, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    client, headers, app = rbac_client
    target = await seed(memory_session)
    await memory_session.commit()

    async def fail_commit(session):
        # 先 flush 真实删除和新增日志，再模拟提交失败，验证依赖会回滚两者。
        await session.flush()
        raise RuntimeError('private-commit-error')

    monkeypatch.setattr(AsyncSession, 'commit', fail_commit)
    response = await client.post(PRUNE, headers=headers, json={'before_at': (NOW + timedelta(days=1)).isoformat()})
    assert response.status_code == 500 and 'private-commit-error' not in response.text
    async with app.state.session_factory() as session:
        assert await session.get(EventRecord, target.id) is not None
        assert not list((await session.scalars(select(EventRecord).where(EventRecord.action == 'prune_operation_audit'))).all())
