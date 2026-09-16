import json

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from ops.models import MetricDataSource
from eventwall.models import EventRecord
from rbac.models import PermissionDefinition, Role, User
from rbac.services.accounts import issue_token
from aidevops.config_secrets import ENVELOPE
from tests_fastapi.integration.test_rbac_reads import rbac_client


ROOT = "/api/observability/metric/datasources/"


@pytest.fixture
def config_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("AIOPS_CONFIG_ENCRYPTION_KEY", key)
    return key


# 构造与现有 MetricsQuery.vue 完全一致的数据源提交结构。
def frontend_payload(name="prod", environment="prod", *, default=True, password="secret", token=""):
    headers = {"X-Tenant": "tenant-secret"}
    return {
        "name": name,
        "provider": "prometheus",
        "description": "生产指标",
        "environment": environment,
        "cluster_name": "cluster-a",
        "tsdb_type": "prometheus",
        "is_enabled": True,
        "is_default": default,
        "config": {
            "query_url": "https://prom.example.com",
            "prometheus.addr": "https://prom.example.com",
            "auth_type": "basic" if password else ("bearer" if token else "none"),
            "username": "reader",
            "password": password,
            "bearer_token": token,
            "headers": headers,
            "prometheus.headers": headers,
            "timeout": 6,
            "prometheus.timeout": 6,
            "tls_skip_verify": False,
            "prometheus.basic": {
                "prometheus.user": "reader",
                "prometheus.password": password,
            },
        },
    }


# 创建只拥有一个指标权限的普通账号，验证三类权限不会互相扩张。
async def permission_headers(session, code, suffix):
    permission = await session.scalar(select(PermissionDefinition).where(PermissionDefinition.code == code))
    role = Role(name=f"metric-{suffix}", code=f"metric-{suffix}", permissions=[permission])
    user = User(username=f"metric-{suffix}", password_hash="unused", roles=[role])
    session.add(user)
    await session.flush()
    token = await issue_token(session, user)
    await session.commit()
    return {"Authorization": f"Token {token}"}


# 完整 CRUD 保留前端字段形状，数据库只保存密文且页面往返掩码可保留原凭据。
@pytest.mark.asyncio
async def test_crud_frontend_round_trip_encrypts_and_preserves_secrets(rbac_client, config_key):
    client, headers, app = rbac_client
    created = await client.post(ROOT, headers=headers, json=frontend_payload())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["provider_display"] == "Prometheus"
    assert body["config"]["query_url"] == "https://prom.example.com"
    assert body["config"]["password"] == "***"
    assert body["config"]["headers"]["X-Tenant"] == "***"
    assert body["config"]["prometheus.basic"]["prometheus.password"] == "***"
    identifier = body["id"]

    async with app.state.session_factory() as session:
        stored = await session.get(MetricDataSource, identifier)
        encoded = json.dumps(stored.config)
        assert '"secret"' not in encoded and "tenant-secret" not in encoded
        assert ENVELOPE in stored.config["password"]

    body["description"] = "changed"
    updated = await client.put(f"{ROOT}{identifier}/", headers=headers, json=body)
    assert updated.status_code == 200, updated.text
    assert updated.json()["description"] == "changed"
    assert updated.json()["config"]["password"] == "***"
    cleared = await client.patch(
        f"{ROOT}{identifier}/",
        headers=headers,
        json={"config": {**body["config"], "password": "", "prometheus.basic": {"prometheus.user": "reader", "prometheus.password": ""}}},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["config"]["password"] == ""
    assert (await client.delete(f"{ROOT}{identifier}/", headers=headers)).status_code == 204
    assert (await client.get(f"{ROOT}{identifier}/", headers=headers)).status_code == 404


# PATCH 未提交 config 时必须保留已有密文，并允许修改普通字段。
@pytest.mark.asyncio
async def test_patch_without_config_preserves_encrypted_secrets(rbac_client, config_key):
    client, headers, app = rbac_client
    created = await client.post(ROOT, headers=headers, json=frontend_payload("patch-secret"))
    assert created.status_code == 201
    identifier = created.json()["id"]
    async with app.state.session_factory() as session:
        before = (await session.get(MetricDataSource, identifier)).config
    response = await client.patch(f"{ROOT}{identifier}/", headers=headers, json={"description": "only text"})
    assert response.status_code == 200, response.text
    async with app.state.session_factory() as session:
        after = (await session.get(MetricDataSource, identifier)).config
    assert after["password"] == before["password"]
    assert after["headers"] == before["headers"]


# PATCH 只提交 config 的一个普通字段时继承服务器密文，不把旧 envelope 当作客户端伪造值。
@pytest.mark.asyncio
async def test_partial_config_patch_preserves_server_secrets(rbac_client, config_key):
    client, headers, app = rbac_client
    created = await client.post(ROOT, headers=headers, json=frontend_payload("partial-config"))
    identifier = created.json()["id"]
    async with app.state.session_factory() as session:
        before = (await session.get(MetricDataSource, identifier)).config
    response = await client.patch(f"{ROOT}{identifier}/", headers=headers, json={"config": {"timeout": 10}})
    assert response.status_code == 200, response.text
    assert response.json()["config"]["timeout"] == 10
    async with app.state.session_factory() as session:
        after = (await session.get(MetricDataSource, identifier)).config
    assert after["password"] == before["password"]
    assert after["headers"] == before["headers"]


# 旧库即使存在嵌套敏感键，读取投影也不能回显明文。
@pytest.mark.asyncio
async def test_legacy_nested_sensitive_values_are_masked(rbac_client, memory_session):
    client, headers, _ = rbac_client
    row = MetricDataSource(
        name="legacy-nested",
        config={"query_url": "https://legacy.example.com", "prometheus": {"headers": {"Authorization": "legacy-secret"}}},
    )
    memory_session.add(row)
    await memory_session.commit()
    response = await client.get(f"{ROOT}{row.id}/", headers=headers)
    assert response.status_code == 200
    assert "legacy-secret" not in response.text
    assert response.json()["config"]["prometheus"]["headers"]["Authorization"] == "***"


# query-only 用户只得到下拉选择字段，view 用户才能读取脱敏配置，详情仍需 view。
@pytest.mark.asyncio
async def test_list_permission_uses_safe_or_full_projection(rbac_client, memory_session, config_key):
    client, admin_headers, _ = rbac_client
    created = await client.post(ROOT, headers=admin_headers, json=frontend_payload())
    assert created.status_code == 201
    query_headers = await permission_headers(memory_session, "ops.metric.query", "query")
    view_headers = await permission_headers(memory_session, "ops.metric.datasource.view", "view")
    manage_headers = await permission_headers(memory_session, "ops.metric.datasource.manage", "manage")

    query_result = await client.get(ROOT, headers=query_headers)
    assert query_result.status_code == 200
    assert set(query_result.json()[0]) == {
        "id",
        "name",
        "provider",
        "provider_display",
        "description",
        "environment",
        "cluster_name",
        "tsdb_type",
        "is_enabled",
        "is_default",
    }
    view_result = await client.get(ROOT, headers=view_headers)
    assert view_result.status_code == 200 and view_result.json()[0]["config"]["password"] == "***"
    identifier = created.json()["id"]
    assert (await client.get(f"{ROOT}{identifier}/", headers=query_headers)).status_code == 403

    managed = await client.post(ROOT, headers=manage_headers, json=frontend_payload("managed", "dev", default=False))
    assert managed.status_code == 201 and "config" not in managed.json()
    assert (await client.get(ROOT, headers=manage_headers)).status_code == 403
    assert (await client.get(ROOT)).status_code == 401


# 列表筛选稳定排序，且同一 environment 新默认项原子取消旧默认项。
@pytest.mark.asyncio
async def test_filters_and_one_default_per_environment(rbac_client, config_key):
    client, headers, _ = rbac_client
    first = await client.post(ROOT, headers=headers, json=frontend_payload("z-default"))
    second = await client.post(ROOT, headers=headers, json=frontend_payload("a-default"))
    await client.post(ROOT, headers=headers, json=frontend_payload("dev", "dev", default=False))
    assert first.status_code == second.status_code == 201
    prod = await client.get(ROOT, headers=headers, params={"environment": "prod", "is_enabled": "true"})
    assert [item["name"] for item in prod.json()] == ["a-default", "z-default"]
    assert [item["is_default"] for item in prod.json()] == [True, False]
    searched = await client.get(ROOT, headers=headers, params={"search": "z-"})
    assert [item["name"] for item in searched.json()] == ["z-default"]


# 旧明文配置读取时只脱敏不写库，首次编辑后整体升级为密文。
@pytest.mark.asyncio
async def test_legacy_plaintext_is_masked_then_upgraded_on_write(rbac_client, memory_session, config_key):
    client, headers, _ = rbac_client
    row = MetricDataSource(
        name="legacy",
        config={"query_url": "https://legacy.example.com", "auth_type": "basic", "username": "reader", "password": "legacy-secret"},
    )
    memory_session.add(row)
    await memory_session.commit()
    identifier = row.id
    response = await client.get(f"{ROOT}{identifier}/", headers=headers)
    assert response.status_code == 200 and response.json()["config"]["password"] == "***"
    memory_session.expire_all()
    assert (await memory_session.get(MetricDataSource, identifier)).config["password"] == "legacy-secret"
    edited = await client.patch(f"{ROOT}{identifier}/", headers=headers, json={"description": "upgrade"})
    assert edited.status_code == 200
    memory_session.expire_all()
    assert ENVELOPE in (await memory_session.get(MetricDataSource, identifier)).config["password"]


# 缺少加密密钥不影响无秘密配置，但有秘密写入必须安全失败且不回显原值。
@pytest.mark.asyncio
async def test_missing_key_only_blocks_secret_writes(rbac_client, monkeypatch):
    monkeypatch.delenv("AIOPS_CONFIG_ENCRYPTION_KEY", raising=False)
    client, headers, _ = rbac_client
    safe = frontend_payload("safe", default=False, password="")
    safe["config"]["headers"] = {}
    safe["config"]["prometheus.headers"] = {}
    assert (await client.post(ROOT, headers=headers, json=safe)).status_code == 201
    failed = await client.post(ROOT, headers=headers, json=frontend_payload("secret-write"))
    assert failed.status_code == 503 and "secret" not in failed.text
    assert len((await client.get(ROOT, headers=headers)).json()) == 1


# 配置审计失败必须回滚实体和默认项变化，审计元数据不包含秘密。
@pytest.mark.asyncio
async def test_config_audit_is_safe_and_failure_rolls_back(rbac_client, monkeypatch, config_key):
    from ops.observability.metrics import config_service as metric_config

    client, headers, app = rbac_client
    created = await client.post(ROOT, headers=headers, json=frontend_payload("audited"))
    assert created.status_code == 201
    async with app.state.session_factory() as session:
        event = await session.scalar(select(EventRecord).where(EventRecord.resource_type == "metric_datasource"))
        assert event is not None
        serialized = json.dumps(event.event_metadata)
        assert "secret" not in serialized and "tenant-secret" not in serialized

    async def fail(*args, **kwargs):
        raise RuntimeError("private-audit-error")

    monkeypatch.setattr(metric_config, "record_event", fail)
    failed = await client.post(ROOT, headers=headers, json=frontend_payload("rollback", "dev"))
    assert failed.status_code == 500 and "private-audit-error" not in failed.text
    names = [item["name"] for item in (await client.get(ROOT, headers=headers)).json()]
    assert names == ["audited"]
