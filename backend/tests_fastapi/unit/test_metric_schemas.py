from datetime import datetime, timezone

import pytest
from pydantic import ValidationError


def schemas():
    from ops.observability.metrics.schemas import (
        MetricConnectionTest,
        MetricDataSourceCreate,
        MetricDataSourcePatch,
        MetricQuery,
        MetricSeriesNames,
    )

    return MetricConnectionTest, MetricDataSourceCreate, MetricDataSourcePatch, MetricQuery, MetricSeriesNames


# 查询请求兼容旧页面别名，并将正式字段标准化供服务层使用。
def test_query_aliases_normalize_to_one_contract():
    _, _, _, MetricQuery, _ = schemas()
    body = MetricQuery.model_validate(
        {
            "query": " rate(http_requests_total[5m]) ",
            "datasource_id": 7,
            "range": True,
            "start_time": "2026-09-16T00:00:00+08:00",
            "end_time": "2026-09-16T00:30:00+08:00",
            "step": 30,
        }
    )

    assert body.promql == "rate(http_requests_total[5m])"
    assert body.metric_datasource_id == 7
    assert body.range_query is True
    assert body.start == datetime(2026, 9, 15, 16, 0, tzinfo=timezone.utc)
    assert body.end == datetime(2026, 9, 15, 16, 30, tzinfo=timezone.utc)


# 数据源 schema 忽略页面往返展示字段，但拒绝真正未知的输入字段。
def test_datasource_round_trip_fields_are_ignored_and_unknown_fields_fail():
    _, MetricDataSourceCreate, _, _, _ = schemas()
    body = MetricDataSourceCreate.model_validate(
        {
            "id": 9,
            "created_at": "2026-09-16T00:00:00Z",
            "updated_at": "2026-09-16T00:00:00Z",
            "provider_display": "Prometheus",
            "name": " prod ",
            "config": {"query_url": "https://prom.example.com"},
        }
    )

    assert body.name == "prod"
    with pytest.raises(ValidationError):
        MetricDataSourceCreate.model_validate({"name": "prod", "unexpected": True})


# 自定义请求头不能覆盖连接层负责维护的逐跳和目标请求头。
@pytest.mark.parametrize("header", ["Host", "content-length", "Connection", "Transfer-Encoding", "Proxy-Authorization"])
def test_protected_header_is_rejected(header):
    _, MetricDataSourceCreate, _, _, _ = schemas()
    with pytest.raises(ValidationError):
        MetricDataSourceCreate.model_validate(
            {
                "name": "prod",
                "config": {"query_url": "https://prom.example.com", "headers": {header: "evil"}},
            }
        )


# 前端实际使用点号兼容键提交 headers，该路径必须遵守相同保护规则。
def test_dotted_prometheus_headers_are_validated():
    _, MetricDataSourceCreate, _, _, _ = schemas()
    with pytest.raises(ValidationError):
        MetricDataSourceCreate.model_validate(
            {
                "name": "prod",
                "config": {"prometheus.headers": {"Host": "evil"}},
            }
        )


# 不支持的嵌套 prometheus 结构必须拒绝，避免秘密绕过正式 dotted 路径处理。
def test_nested_prometheus_config_is_rejected():
    _, MetricDataSourceCreate, _, _, _ = schemas()
    with pytest.raises(ValidationError):
        MetricDataSourceCreate.model_validate(
            {
                "name": "prod",
                "config": {"prometheus": {"headers": {"Authorization": "example-secret"}}},
            }
        )


# 配置必须遵守大小、嵌套和头字段数量上限，防止 JSON 列承载无界输入。
def test_config_limits_are_enforced():
    _, MetricDataSourceCreate, _, _, _ = schemas()
    with pytest.raises(ValidationError):
        MetricDataSourceCreate.model_validate({"name": "prod", "config": {"value": "x" * 70_000}})
    deep = value = {}
    for _ in range(21):
        value["child"] = {}
        value = value["child"]
    with pytest.raises(ValidationError):
        MetricDataSourceCreate.model_validate({"name": "prod", "config": deep})
    with pytest.raises(ValidationError):
        MetricDataSourceCreate.model_validate(
            {"name": "prod", "config": {"headers": {f"X-Test-{index}": "v" for index in range(65)}}}
        )


# provider、tsdb_type、布尔和 URL 采用严格边界，避免隐式类型转换改变连接策略。
def test_datasource_core_fields_are_strict():
    _, MetricDataSourceCreate, _, _, _ = schemas()
    for values in (
        {"name": "prod", "provider": "victoriametrics"},
        {"name": "prod", "tsdb_type": "influxdb"},
        {"name": "prod", "is_enabled": 1},
        {"name": "prod", "config": {"query_url": "x" * 2049}},
        {"name": "prod", "config": {"tls_skip_verify": "false"}},
        {"name": "prod", "config": {"timeout": True}},
        {"name": "prod", "config": {"timeout": 31}},
        {"name": "prod", "config": {"auth_type": []}},
        {"name": "prod", "config": {"auth_type": {}}},
    ):
        with pytest.raises(ValidationError):
            MetricDataSourceCreate.model_validate(values)


# 查询边界限制 PromQL、步长、时间顺序和最长区间。
def test_query_bounds_are_enforced():
    _, _, _, MetricQuery, _ = schemas()
    with pytest.raises(ValidationError):
        MetricQuery.model_validate({"promql": " "})
    with pytest.raises(ValidationError):
        MetricQuery.model_validate({"promql": "x", "step": 0})
    with pytest.raises(ValidationError):
        MetricQuery.model_validate(
            {
                "promql": "up",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-02-02T00:00:00Z",
            }
        )
    with pytest.raises(ValidationError):
        MetricQuery.model_validate({"promql": "up", "query_type": []})
    with pytest.raises(ValidationError):
        MetricQuery.model_validate({"promql": "up", "query_type": {}})


# 指标名与连接测试参数有界，PATCH 只保留显式字段。
def test_series_connection_and_patch_contracts():
    MetricConnectionTest, _, MetricDataSourcePatch, _, MetricSeriesNames = schemas()
    assert MetricConnectionTest().query == "up"
    assert MetricSeriesNames().limit == 80
    assert MetricSeriesNames.model_validate({"datasource_id": 4, "keyword": "http", "limit": 200}).metric_datasource_id == 4
    assert MetricDataSourcePatch.model_validate({"description": "changed"}).model_dump(exclude_unset=True) == {
        "description": "changed"
    }
    with pytest.raises(ValidationError):
        MetricSeriesNames.model_validate({"limit": 201})


# PATCH 可省略字段但不能把数据库非空字段显式写为 null。
@pytest.mark.parametrize("field", ["name", "provider", "description", "environment", "cluster_name", "tsdb_type", "config", "is_enabled", "is_default"])
def test_patch_rejects_explicit_null(field):
    _, _, MetricDataSourcePatch, _, _ = schemas()
    with pytest.raises(ValidationError):
        MetricDataSourcePatch.model_validate({field: None})


# 页面尚未选中数据源时会发送空字符串，服务端应归一为空并执行默认选择。
def test_blank_datasource_identifier_normalizes_to_none():
    _, _, _, MetricQuery, MetricSeriesNames = schemas()
    assert MetricQuery.model_validate({"promql": "up", "metric_datasource_id": ""}).metric_datasource_id is None
    assert MetricSeriesNames.model_validate({"datasource_id": ""}).metric_datasource_id is None
