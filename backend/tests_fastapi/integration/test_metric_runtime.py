import asyncio
import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from ops.models import MetricDataSource
from eventwall.models import EventRecord
from rbac.models import User
from tests_fastapi.integration.test_metric_config import config_key, frontend_payload
from tests_fastapi.integration.test_rbac_reads import rbac_client


DATA_SOURCES = "/api/observability/metric/datasources/"
QUERY = "/api/observability/metrics/query/"
SERIES = "/api/observability/metrics/series-names/"


# 用内存传输替代真实网络，同时保留 DNS 准入和 HTTP 请求形状验证。
def network(monkeypatch, handler, addresses=None):
    from ops.observability.metrics import runtime as metric_runtime

    async def resolved(target):
        return addresses or ["8.8.8.8"]

    monkeypatch.setattr(metric_runtime, "resolve_addresses", resolved)

    def transport(**kwargs):
        result = httpx.MockTransport(handler)
        result._pool = SimpleNamespace(_network_backend=None)
        return result

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)


# 创建可运行数据源并返回其 ID。
async def create_source(client, headers, *, name="runtime", environment="prod", default=True):
    response = await client.post(DATA_SOURCES, headers=headers, json=frontend_payload(name, environment, default=default))
    assert response.status_code == 201, response.text
    return response.json()["id"]


# 区间查询使用编码参数和解密后的 Basic/header，返回前端需要的矩阵及安全审计。
@pytest.mark.asyncio
async def test_range_query_contract_auth_and_safe_audit(rbac_client, monkeypatch, config_key):
    client, headers, app = rbac_client
    identifier = await create_source(client, headers)
    requests = []

    def reply(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "resultType": "matrix",
                    "result": [
                        {"metric": {"__name__": "up", "job": "api"}, "values": [[1, "1"], [2, "0"]]}
                    ],
                },
            },
        )

    network(monkeypatch, reply)
    response = await client.post(
        QUERY,
        headers=headers,
        json={
            "metric_datasource_id": identifier,
            "promql": "up",
            "range_query": True,
            "start": "2026-09-16T00:00:00Z",
            "end": "2026-09-16T00:05:00Z",
            "step": 30,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resultType"] == "matrix" and body["series_count"] == 1
    assert body["result"][0]["values"][-1] == [2, "0"]
    assert body["metric_datasource"]["id"] == identifier and "config" not in body["metric_datasource"]
    assert requests[0].url.path == "/api/v1/query_range"
    assert requests[0].url.params["query"] == "up" and requests[0].url.params["step"] == "30"
    expected_basic = base64.b64encode(b"reader:secret").decode()
    assert requests[0].headers["Authorization"] == f"Basic {expected_basic}"
    assert requests[0].headers["X-Tenant"] == "tenant-secret"
    assert requests[0].headers["Accept-Encoding"] == "identity"

    async with app.state.session_factory() as session:
        event = await session.scalar(select(EventRecord).where(EventRecord.action == "query_metrics"))
        assert event is not None
        metadata = json.dumps(event.event_metadata)
        assert "up" not in metadata and "secret" not in metadata
        assert event.event_metadata["query_length"] == 2
        assert isinstance(event.event_metadata["duration_ms"], int)


# 指标名补全执行不区分大小写过滤、去重、排序和 limit，且不制造查询审计。
@pytest.mark.asyncio
async def test_series_names_filter_sort_limit_without_audit(rbac_client, monkeypatch, config_key):
    client, headers, app = rbac_client
    identifier = await create_source(client, headers)
    network(
        monkeypatch,
        lambda request: httpx.Response(200, json={"status": "success", "data": ["z_total", "HTTP_total", "http_requests", "HTTP_total"]}),
    )
    response = await client.get(
        SERIES,
        headers=headers,
        params={"metric_datasource_id": identifier, "q": "http", "limit": 2},
    )
    assert response.status_code == 200, response.text
    assert response.json()["metrics"] == ["HTTP_total", "http_requests"]
    assert response.json()["count"] == 2
    async with app.state.session_factory() as session:
        assert await session.scalar(select(EventRecord).where(EventRecord.action == "list_metric_names")) is None


# 即时查询将 vector/scalar/string 统一成页面可遍历的 series 结构。
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result_type,result,expected_value",
    [
        ("vector", [{"metric": {"job": "api"}, "value": [2, "1"]}], [2, "1"]),
        ("scalar", [2, "3.5"], [2, "3.5"]),
        ("string", [2, "healthy"], [2, "healthy"]),
    ],
)
async def test_instant_result_types_are_normalized(rbac_client, monkeypatch, config_key, result_type, result, expected_value):
    client, headers, _ = rbac_client
    identifier = await create_source(client, headers)
    network(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={"status": "success", "data": {"resultType": result_type, "result": result}},
        ),
    )
    response = await client.post(
        QUERY,
        headers=headers,
        json={"metric_datasource_id": identifier, "promql": "up", "range_query": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"][0]["value"] == expected_value


# 连接测试复用即时查询但只返回安全摘要，不保存远端原文。
@pytest.mark.asyncio
async def test_connection_test_returns_safe_summary(rbac_client, monkeypatch, config_key):
    client, headers, app = rbac_client
    identifier = await create_source(client, headers)
    network(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={"status": "success", "data": {"resultType": "vector", "result": [{"metric": {"job": "private"}, "value": [2, "1"]}]}},
        ),
    )
    response = await client.post(f"{DATA_SOURCES}{identifier}/test_connection/", headers=headers, json={"query": "up"})
    assert response.status_code == 200, response.text
    assert response.json()["success"] is True and response.json()["series_count"] == 1
    async with app.state.session_factory() as session:
        event = await session.scalar(select(EventRecord).where(EventRecord.action == "test_metric_datasource"))
        assert event is not None and "private" not in json.dumps(event.event_metadata)


# 未授权私网和混合 DNS 在发送凭据前失败，allowlist 也不能授权链路本地元数据地址。
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "allowed,addresses",
    [
        ("[]", ["127.0.0.1"]),
        ('["https://prom.example.com"]', ["8.8.8.8", "127.0.0.1"]),
        ('["https://prom.example.com"]', ["169.254.169.254"]),
    ],
)
async def test_address_admission_fails_before_network(rbac_client, monkeypatch, config_key, allowed, addresses):
    client, headers, _ = rbac_client
    identifier = await create_source(client, headers)
    monkeypatch.setenv("AIOPS_METRIC_ALLOWED_ORIGINS", allowed)
    calls = []
    network(monkeypatch, lambda request: calls.append(request) or httpx.Response(200, json={}), addresses)
    response = await client.post(QUERY, headers=headers, json={"metric_datasource_id": identifier, "promql": "up"})
    assert response.status_code in {400, 502} and not calls
    assert "secret" not in response.text


# Prometheus 错误 envelope、非 JSON 和序列上限都转换为不回显远端正文的 502。
@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["envelope", "non-json", "too-many-series"])
async def test_remote_protocol_failures_are_safe(rbac_client, monkeypatch, config_key, mode):
    client, headers, _ = rbac_client
    identifier = await create_source(client, headers)

    def reply(request):
        if mode == "envelope":
            return httpx.Response(200, json={"status": "error", "error": "remote-private-secret"})
        if mode == "non-json":
            return httpx.Response(200, text="remote-private-secret")
        result = [{"metric": {"id": str(index)}, "value": [1, "1"]} for index in range(1001)]
        return httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": result}})

    network(monkeypatch, reply)
    response = await client.post(QUERY, headers=headers, json={"metric_datasource_id": identifier, "promql": "up", "range_query": False})
    assert response.status_code == 502
    assert "remote-private-secret" not in response.text


# 非字符串 resultType 必须安全返回 502，并像其他协议失败一样保存固定失败审计。
@pytest.mark.asyncio
@pytest.mark.parametrize("result_type", [[], {}])
async def test_unhashable_result_type_is_safe_and_audited(rbac_client, monkeypatch, config_key, result_type):
    client, headers, app = rbac_client
    identifier = await create_source(client, headers)
    network(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={"status": "success", "data": {"resultType": result_type, "result": []}},
        ),
    )
    response = await client.post(QUERY, headers=headers, json={"metric_datasource_id": identifier, "promql": "up"})
    assert response.status_code == 502
    async with app.state.session_factory() as session:
        event = await session.scalar(select(EventRecord).where(EventRecord.action == "query_metrics"))
        assert event is not None and event.event_metadata["result"] == "failed"


# 正文和数据点分别受独立上限保护，远端失败也只写固定分类安全审计。
@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["body", "points"])
async def test_response_limits_and_failed_audit(rbac_client, monkeypatch, config_key, mode):
    from ops.observability.metrics import runtime as metric_runtime

    client, headers, app = rbac_client
    identifier = await create_source(client, headers)
    if mode == "body":
        monkeypatch.setattr(metric_runtime, "MAX_RESPONSE_BYTES", 100)
        reply = lambda request: httpx.Response(200, content=b"{" + b"x" * 200)
    else:
        monkeypatch.setattr(metric_runtime, "MAX_POINTS", 2)
        reply = lambda request: httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"resultType": "matrix", "result": [{"metric": {}, "values": [[1, "1"], [2, "2"], [3, "3"]]}]},
            },
        )
    network(monkeypatch, reply)
    response = await client.post(QUERY, headers=headers, json={"metric_datasource_id": identifier, "promql": "private-query"})
    assert response.status_code == 502 and "private-query" not in response.text
    async with app.state.session_factory() as session:
        events = list((await session.scalars(select(EventRecord).where(EventRecord.action == "query_metrics"))).all())
        assert len(events) == 1
        assert events[0].event_metadata["result"] == "failed"
        serialized = json.dumps(events[0].event_metadata)
        assert "private-query" not in serialized and "secret" not in serialized


# 网络返回前配置发生变化时丢弃旧结果，修改后改回也因密文指纹变化而失效。
@pytest.mark.asyncio
async def test_inflight_configuration_change_invalidates_result(rbac_client, monkeypatch, config_key):
    client, headers, app = rbac_client
    identifier = await create_source(client, headers)
    entered, gate = asyncio.Event(), asyncio.Event()

    async def reply(request):
        entered.set()
        await gate.wait()
        return httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": []}})

    network(monkeypatch, reply)
    pending = asyncio.create_task(client.post(QUERY, headers=headers, json={"metric_datasource_id": identifier, "promql": "up"}))
    await asyncio.wait_for(entered.wait(), 2)
    current = (await client.get(f"{DATA_SOURCES}{identifier}/", headers=headers)).json()
    for url in ("https://other.example.com", "https://prom.example.com"):
        current["config"]["query_url"] = url
        current["config"]["prometheus.addr"] = url
        changed = await client.put(f"{DATA_SOURCES}{identifier}/", headers=headers, json=current)
        assert changed.status_code == 200, changed.text
        current = changed.json()
    gate.set()
    assert (await pending).status_code == 409
    async with app.state.session_factory() as session:
        event = await session.scalar(select(EventRecord).where(EventRecord.action == "query_metrics"))
        assert event is not None
        assert event.event_metadata["result"] == "rejected"
        assert event.event_metadata["failure_category"] == "configuration_changed"


# 网络返回前账号被停用时丢弃结果并返回 403。
@pytest.mark.asyncio
async def test_inflight_actor_disable_invalidates_result(rbac_client, monkeypatch, memory_session, config_key):
    client, headers, app = rbac_client
    identifier = await create_source(client, headers)
    entered, gate = asyncio.Event(), asyncio.Event()

    async def reply(request):
        entered.set()
        await gate.wait()
        return httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": []}})

    network(monkeypatch, reply)
    pending = asyncio.create_task(client.post(QUERY, headers=headers, json={"metric_datasource_id": identifier, "promql": "up"}))
    await asyncio.wait_for(entered.wait(), 2)
    admin = await memory_session.scalar(select(User).where(User.username == "admin"))
    admin.is_active = False
    await memory_session.commit()
    gate.set()
    assert (await pending).status_code == 403
    async with app.state.session_factory() as session:
        event = await session.scalar(select(EventRecord).where(EventRecord.action == "query_metrics"))
        assert event is not None
        assert event.event_metadata["result"] == "rejected"
        assert event.event_metadata["failure_category"] == "authorization_changed"


# 旧库中的非布尔 TLS 值不能通过 Python 真值规则意外关闭证书验证。
@pytest.mark.asyncio
async def test_legacy_non_boolean_tls_is_rejected_before_network(rbac_client, monkeypatch, memory_session, config_key):
    client, headers, _ = rbac_client
    row = MetricDataSource(
        name="legacy-tls",
        config={"query_url": "https://prom.example.com", "auth_type": "none", "tls_skip_verify": "false"},
    )
    memory_session.add(row)
    await memory_session.commit()
    calls = []
    network(monkeypatch, lambda request: calls.append(request) or httpx.Response(200, json={}))
    response = await client.post(QUERY, headers=headers, json={"metric_datasource_id": row.id, "promql": "up"})
    assert response.status_code == 400 and not calls
