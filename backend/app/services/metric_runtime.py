# 安全执行 Prometheus 只读请求，并在返回结果前复核账号权限和配置版本。

import asyncio
import base64
import hashlib
import ipaddress
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
from cryptography.fernet import InvalidToken
from dotenv import dotenv_values
from fastapi import HTTPException

from app.models import MetricDataSource, User
from app.schemas.metrics import MetricConnectionTest, MetricQuery, MetricSeriesNames
from app.selectors.metrics import choose_data_source, project_data_source
from app.selectors.permissions import user_has_permissions
from app.services import model_client
from app.services.config_secrets import ENVELOPE, config_cipher
from app.services.events import record_event


MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_SERIES = 1000
MAX_POINTS = 250_000
PROMETHEUS_RESULT_TYPES = frozenset({"matrix", "vector", "scalar", "string"})
SAFE_REMOTE_FAILURE = "Prometheus 请求失败，请检查指标数据源配置。"
PROMETHEUS_CONCURRENCY = asyncio.Semaphore(16)
resolve_addresses = model_client.resolve_addresses


@dataclass(frozen=True)
class MetricSnapshot:
    identifier: int
    actor_id: int
    state: dict[str, object]
    runtime: dict[str, object]
    fingerprint: str
    public: dict[str, object]
    actor_username: str
    actor_display: str


# 将持久化连接状态规范化为内存指纹，不记录或输出指纹内容。
def metric_fingerprint(state: dict[str, object]) -> str:
    canonical = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# 提取影响远端请求的持久化字段，同时加入单调更新时间识别修改后改回。
def persisted_state(item: MetricDataSource) -> dict[str, object]:
    return {
        "id": item.id,
        "provider": item.provider,
        "tsdb_type": item.tsdb_type,
        "config": item.config,
        "is_enabled": item.is_enabled,
        "updated_at": item.updated_at,
    }


# 解密服务端密文并兼容旧明文；密钥缺失沿用 503，损坏密文安全返回 400。
def reveal_secret(value) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict) or set(value) != {ENVELOPE} or not isinstance(value[ENVELOPE], str):
        raise HTTPException(status_code=400, detail="指标数据源凭据格式无效。")
    try:
        return config_cipher().decrypt(value[ENVELOPE].encode()).decode()
    except HTTPException:
        raise
    except (InvalidToken, UnicodeError, ValueError):
        raise HTTPException(status_code=400, detail="指标数据源凭据无法解密。") from None


# 从规范化 config 构造只在运行内存存在的地址、认证、headers 和超时参数。
def runtime_config(config: object) -> dict[str, object]:
    if not isinstance(config, dict):
        raise HTTPException(status_code=400, detail="指标数据源连接配置无效。")
    url = config.get("query_url") or config.get("prometheus.addr")
    if not isinstance(url, str) or not url.strip():
        raise HTTPException(status_code=400, detail="指标数据源查询地址未配置。")
    raw_timeout = config.get("timeout", config.get("prometheus.timeout", 6))
    if isinstance(raw_timeout, bool) or not isinstance(raw_timeout, (int, float)):
        raise HTTPException(status_code=400, detail="指标数据源超时配置无效。") from None
    timeout = float(raw_timeout)
    if not math.isfinite(timeout) or not 1 <= timeout <= 30:
        raise HTTPException(status_code=400, detail="指标数据源超时必须在 1 到 30 秒之间。")
    raw_headers = config.get("headers", config.get("prometheus.headers", {}))
    if not isinstance(raw_headers, dict):
        raise HTTPException(status_code=400, detail="指标数据源请求头配置无效。")
    headers = {str(name): reveal_secret(value) for name, value in raw_headers.items()}
    basic = config.get("prometheus.basic") if isinstance(config.get("prometheus.basic"), dict) else {}
    tls_skip_verify = config.get("tls_skip_verify", False)
    if type(tls_skip_verify) is not bool:
        raise HTTPException(status_code=400, detail="指标数据源 TLS 配置无效。")
    return {
        "query_url": url.strip(),
        "auth_type": config.get("auth_type", "none"),
        "username": str(config.get("username") or basic.get("prometheus.user") or ""),
        "password": reveal_secret(config.get("password", basic.get("prometheus.password"))),
        "bearer_token": reveal_secret(config.get("bearer_token")),
        "headers": headers,
        "timeout": timeout,
        "tls_skip_verify": tls_skip_verify,
    }


# 在短数据库会话内选择数据源并构造快照，关闭会话后才允许网络等待。
async def read_metric_snapshot(factory, identifier: int | None, environment: str, actor_id: int) -> MetricSnapshot:
    async with factory() as database:
        actor = await database.get(User, actor_id, populate_existing=True)
        if actor is None:
            raise HTTPException(status_code=403, detail="账号状态已变化。")
        item = await choose_data_source(database, identifier, environment)
        state = persisted_state(item)
        public = project_data_source(item, include_config=False)
    if state["provider"] != "prometheus" or state["tsdb_type"] != "prometheus" or not state["is_enabled"]:
        raise HTTPException(status_code=400, detail="指标数据源未启用或类型不受支持。")
    return MetricSnapshot(
        item.id,
        actor_id,
        state,
        runtime_config(state["config"]),
        metric_fingerprint(state),
        public,
        actor.username,
        actor.display_name,
    )


# 读取独立指标白名单并验证完整 DNS 答案，混合公网/内网答案视为重绑定风险。
async def admitted_metric_target(runtime: dict[str, object]):
    raw = os.environ.get("AIOPS_METRIC_ALLOWED_ORIGINS")
    if raw is None:
        raw = dotenv_values(".env").get("AIOPS_METRIC_ALLOWED_ORIGINS") or "[]"
    try:
        allowed = json.loads(raw)
        if not isinstance(allowed, list) or any(not isinstance(value, str) for value in allowed):
            raise ValueError()
        target = model_client.validate_origin(str(runtime["query_url"]), allowed)
        addresses = await resolve_addresses(target)
        addresses = model_client.validate_addresses(addresses, target.internal_allowed)
        scopes = {ipaddress.ip_address(value).is_global for value in addresses}
        if len(scopes) > 1:
            raise ValueError()
        return target, addresses
    except (ValueError, OSError):
        raise HTTPException(status_code=400, detail="指标数据源地址未通过服务端准入检查。") from None


# 构造 Basic、Bearer 或自定义认证请求头，控制字符一律拒绝。
def request_headers(runtime: dict[str, object]) -> dict[str, str]:
    headers = {str(name): str(value) for name, value in runtime["headers"].items()}
    auth_type = runtime["auth_type"]
    if auth_type == "basic":
        username, password = str(runtime["username"]), str(runtime["password"])
        if not username or not password:
            raise HTTPException(status_code=400, detail="Basic 认证账号或密码未配置。")
        headers["Authorization"] = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
    elif auth_type == "bearer":
        token = str(runtime["bearer_token"])
        if not token:
            raise HTTPException(status_code=400, detail="Bearer Token 未配置。")
        headers["Authorization"] = "Bearer " + token
    elif auth_type != "none":
        raise HTTPException(status_code=400, detail="指标数据源认证方式无效。")
    if any(any(ord(character) < 32 or ord(character) == 127 for character in value) for value in headers.values()):
        raise HTTPException(status_code=400, detail="指标数据源请求头包含非法字符。")
    headers.update({"Accept": "application/json", "Accept-Encoding": "identity"})
    return headers


# 使用固定 IP、禁代理/重定向/重试的客户端读取有界 JSON 响应。
async def request_prometheus(snapshot: MetricSnapshot, suffix: str, params: dict[str, object]) -> object:
    runtime = snapshot.runtime
    budget = float(runtime["timeout"])
    try:
        async with asyncio.timeout(budget):
            target, addresses = await admitted_metric_target(runtime)
            transport = httpx.AsyncHTTPTransport(
                verify=not bool(runtime["tls_skip_verify"]),
                trust_env=False,
                retries=0,
            )
            if not hasattr(transport, "_pool") or not hasattr(transport._pool, "_network_backend"):
                await transport.aclose()
                raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE)
            transport._pool._network_backend = model_client.PinnedBackend(target.host, target.port, addresses[0])
            async with PROMETHEUS_CONCURRENCY:
                async with httpx.AsyncClient(
                    transport=transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=budget,
                ) as client:
                    async with client.stream(
                        "GET",
                        target.url + suffix,
                        params=params,
                        headers=request_headers(runtime),
                    ) as response:
                        if not 200 <= response.status_code < 300:
                            raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE)
                        if response.headers.get("content-encoding", "identity").strip().lower() != "identity":
                            raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE)
                        content = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=65_536):
                            content.extend(chunk)
                            if len(content) > MAX_RESPONSE_BYTES:
                                raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE)
        return json.loads(content)
    except asyncio.CancelledError:
        raise
    except HTTPException:
        raise
    except (TimeoutError, httpx.TimeoutException, httpx.HTTPError, OSError, ValueError, UnicodeError, RecursionError):
        raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE) from None


# 验证 Prometheus 查询 envelope，只接受页面能够消费的四类结果。
def validate_prometheus_envelope(payload: object) -> tuple[str, object]:
    if not isinstance(payload, dict) or payload.get("status") != "success" or not isinstance(payload.get("data"), dict):
        raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE)
    data = payload["data"]
    result_type = data.get("resultType")
    if not isinstance(result_type, str) or result_type not in PROMETHEUS_RESULT_TYPES or "result" not in data:
        raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE)
    return result_type, data["result"]


# 校验时间点形状和值类型，避免畸形远端 JSON 进入前端图表。
def validated_point(value: object) -> list[object]:
    if not isinstance(value, list) or len(value) != 2 or not isinstance(value[0], (int, float)) or not math.isfinite(value[0]):
        raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE)
    if not isinstance(value[1], (str, int, float)) or len(str(value[1])) > 1024:
        raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE)
    return [value[0], str(value[1])]


# 将四类结果统一成 series 数组，并在返回前执行序列/数据点上限检查。
def normalize_result(result_type: str, raw: object) -> list[dict[str, object]]:
    if result_type in {"scalar", "string"}:
        rows = [{"metric": {}, "value": validated_point(raw)}]
    else:
        if not isinstance(raw, list):
            raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE)
        rows = []
        for item in raw:
            if not isinstance(item, dict) or not isinstance(item.get("metric", {}), dict):
                raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE)
            labels = item.get("metric", {})
            if any(not isinstance(key, str) or not isinstance(value, str) or len(key) > 256 or len(value) > 4096 for key, value in labels.items()):
                raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE)
            key = "values" if result_type == "matrix" else "value"
            points = item.get(key)
            if result_type == "matrix":
                if not isinstance(points, list):
                    raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE)
                rows.append({"metric": labels, "values": [validated_point(point) for point in points]})
            else:
                rows.append({"metric": labels, "value": validated_point(points)})
    points_count = sum(len(row.get("values", [])) if "values" in row else 1 for row in rows)
    if len(rows) > MAX_SERIES or points_count > MAX_POINTS:
        raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE)
    return rows


# 生成不包含完整远端结果的五条安全摘要。
def sample_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    sample = []
    for row in rows[:5]:
        points = row.get("values") if "values" in row else [row.get("value")]
        sample.append({"labels": row.get("metric", {}), "latest_value": points[-1][1] if points else None, "points": len(points)})
    return sample


# 使用新会话复核账号、权限、数据源状态和指纹，并在成功响应前提交安全审计。
async def finalize_metric_operation(
    factory,
    snapshot: MetricSnapshot,
    request,
    *,
    required_permission: str,
    action: str | None,
    metadata: dict[str, object],
) -> None:
    async with factory() as database:
        actor = await database.get(User, snapshot.actor_id, populate_existing=True)
        item = await database.get(MetricDataSource, snapshot.identifier, populate_existing=True)
        rejection = None
        if actor is None or not actor.is_active or not await user_has_permissions(database, actor, (required_permission,)):
            rejection = (403, "账号或指标权限已变化。", "authorization_changed")
        elif item is None or not item.is_enabled or metric_fingerprint(persisted_state(item)) != snapshot.fingerprint:
            rejection = (409, "指标数据源配置已变化或被删除，请重新查询。", "configuration_changed")
        if rejection is not None:
            if action is not None:
                audit_actor = actor or SimpleNamespace(username=snapshot.actor_username, display_name=snapshot.actor_display)
                rejected_metadata = {
                    **metadata,
                    "result": "rejected",
                    "failure_category": rejection[2],
                }
                await record_event(
                    database,
                    actor=audit_actor,
                    method=request.method,
                    path=request.url.path,
                    ip_address=request.client.host if request.client else "",
                    correlation_id=getattr(request.state, "correlation_id", ""),
                    action=action,
                    title="指标数据源运行",
                    resource_type="metric_datasource",
                    resource_id=str(snapshot.identifier),
                    metadata=rejected_metadata,
                    module="ops",
                    category="observability",
                )
                await database.commit()
            raise HTTPException(status_code=rejection[0], detail=rejection[1])
        if action is not None:
            await record_event(
                database,
                actor=actor,
                method=request.method,
                path=request.url.path,
                ip_address=request.client.host if request.client else "",
                correlation_id=getattr(request.state, "correlation_id", ""),
                action=action,
                title="指标数据源运行",
                resource_type="metric_datasource",
                resource_id=str(snapshot.identifier),
                metadata=metadata,
                module="ops",
                category="observability",
            )
            await database.commit()


# 执行 PromQL 查询，统一默认时间、结果结构、摘要和安全审计。
async def execute_metric_query(factory, actor_id: int, request, body: MetricQuery) -> dict[str, object]:
    snapshot = await read_metric_snapshot(factory, body.metric_datasource_id, body.environment, actor_id)
    started = time.perf_counter()
    now = datetime.now(timezone.utc)
    start = body.start or now - timedelta(minutes=30)
    end = body.end or now
    params: dict[str, object] = {"query": body.promql}
    suffix = "/api/v1/query"
    if body.range_query:
        suffix = "/api/v1/query_range"
        params.update(start=start.timestamp(), end=end.timestamp(), step=body.step)
    try:
        payload = await request_prometheus(snapshot, suffix, params)
        result_type, raw = validate_prometheus_envelope(payload)
        rows = normalize_result(result_type, raw)
    except HTTPException:
        await finalize_metric_operation(
            factory,
            snapshot,
            request,
            required_permission="ops.metric.query",
            action="query_metrics",
            metadata={
                "query_length": len(body.promql),
                "query_type": "range" if body.range_query else "instant",
                "duration_ms": max(0, round((time.perf_counter() - started) * 1000)),
                "series_count": 0,
                "result": "failed",
                "failure_category": "remote_or_protocol",
            },
        )
        raise
    await finalize_metric_operation(
        factory,
        snapshot,
        request,
        required_permission="ops.metric.query",
        action="query_metrics",
        metadata={
            "query_length": len(body.promql),
            "query_type": "range" if body.range_query else "instant",
            "duration_ms": max(0, round((time.perf_counter() - started) * 1000)),
            "series_count": len(rows),
            "result": "success",
        },
    )
    return {
        "query": body.promql,
        "range": body.range_query,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "step": body.step,
        "source": snapshot.public["name"],
        "description": snapshot.public["description"],
        "metric_datasource": snapshot.public,
        "resultType": result_type,
        "result": rows,
        "sample": sample_rows(rows),
        "series_count": len(rows),
    }


# 查询指标名并在本地执行去重、排序、包含过滤和 limit，不写高频审计。
async def list_metric_names(factory, actor_id: int, request, params: MetricSeriesNames) -> dict[str, object]:
    snapshot = await read_metric_snapshot(factory, params.metric_datasource_id, params.environment, actor_id)
    payload = await request_prometheus(snapshot, "/api/v1/label/__name__/values", {})
    if not isinstance(payload, dict) or payload.get("status") != "success" or not isinstance(payload.get("data"), list):
        raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE)
    if any(not isinstance(value, str) or len(value) > 1024 for value in payload["data"]):
        raise HTTPException(status_code=502, detail=SAFE_REMOTE_FAILURE)
    keyword = params.q.casefold()
    metrics = sorted({value for value in payload["data"] if not keyword or keyword in value.casefold()})[: params.limit]
    await finalize_metric_operation(
        factory,
        snapshot,
        request,
        required_permission="ops.metric.query",
        action=None,
        metadata={},
    )
    return {"metrics": metrics, "count": len(metrics), "metric_datasource": snapshot.public}


# 使用即时查询测试连接，只返回安全摘要并保存固定字段审计。
async def test_metric_connection(
    factory,
    actor_id: int,
    request,
    identifier: int,
    body: MetricConnectionTest,
) -> dict[str, object]:
    snapshot = await read_metric_snapshot(factory, identifier, "", actor_id)
    started = time.perf_counter()
    try:
        payload = await request_prometheus(snapshot, "/api/v1/query", {"query": body.query})
        result_type, raw = validate_prometheus_envelope(payload)
        rows = normalize_result(result_type, raw)
    except HTTPException:
        await finalize_metric_operation(
            factory,
            snapshot,
            request,
            required_permission="ops.metric.datasource.manage",
            action="test_metric_datasource",
            metadata={
                "query_length": len(body.query),
                "duration_ms": max(0, round((time.perf_counter() - started) * 1000)),
                "series_count": 0,
                "result": "failed",
                "failure_category": "remote_or_protocol",
            },
        )
        raise
    await finalize_metric_operation(
        factory,
        snapshot,
        request,
        required_permission="ops.metric.datasource.manage",
        action="test_metric_datasource",
        metadata={
            "query_length": len(body.query),
            "duration_ms": max(0, round((time.perf_counter() - started) * 1000)),
            "series_count": len(rows),
            "result": "success",
        },
    )
    return {
        "success": True,
        "message": "指标数据源连接测试成功。",
        "series_count": len(rows),
        "sample": sample_rows(rows),
        "metric_datasource": snapshot.public,
    }
