import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from types import SimpleNamespace
from urllib.parse import quote

from cryptography.fernet import InvalidToken
from fastapi import HTTPException

from aidevops.config_secrets import ENVELOPE, config_cipher
from eventwall.services import record_event
from ops.observability.logs.providers.elk import build_search_body, parse_search
from ops.observability.logs.providers.loki import parse_query
from ops.observability.logs.schemas import parse_elk_index_pattern
from ops.observability.logs.selectors import get_data_source, project_data_source
from ops.observability.logs.transport import LogAddressError, request_json, validate_origin
from ops.models import LogDataSource
from rbac.models import User
from rbac.selectors.permissions import user_has_permissions


@dataclass(frozen=True)
class LogSnapshot:
    identifier: int
    actor_id: int
    provider: str
    config: dict[str, object]
    public: dict[str, object]
    fingerprint: str
    actor_username: str
    actor_display: str


def persisted_state(item: LogDataSource) -> dict[str, object]:
    return {
        "id": item.id,
        "provider": item.provider,
        "config": item.config,
        "is_enabled": item.is_enabled,
        "updated_at": item.updated_at,
    }


def log_fingerprint(state: dict[str, object]) -> str:
    canonical = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def reveal(value):
    if not value:
        return ""
    if isinstance(value, str):
        return value
    try:
        return config_cipher().decrypt(value[ENVELOPE].encode()).decode()
    except (KeyError, InvalidToken, ValueError, UnicodeError):
        raise HTTPException(400, "日志数据源凭据无法解密。") from None


def allowed_origins():
    raw = os.environ.get("AIOPS_LOG_ALLOWED_ORIGINS", "[]")
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except json.JSONDecodeError:
        return [item.strip() for item in raw.split(",") if item.strip()]


async def snapshot(factory, identifier, actor_id, permission):
    async with factory() as session:
        actor = await session.get(User, actor_id)
        if actor is None or not actor.is_active or not await user_has_permissions(session, actor, (permission,)):
            raise HTTPException(403, "账号权限已变化。")
        item = await get_data_source(session, identifier)
        if not item.is_enabled:
            raise HTTPException(400, "日志数据源未启用。")
        state = persisted_state(item)
        config = dict(item.config) if isinstance(item.config, dict) else {}
        for key in ("password", "api_key", "bearer_token", "access_key_id", "access_key_secret"):
            if key in config:
                config[key] = reveal(config[key])
        return LogSnapshot(
            identifier=item.id,
            actor_id=actor_id,
            provider=item.provider,
            config=config,
            public=project_data_source(item, include_config=False),
            fingerprint=log_fingerprint(state),
            actor_username=actor.username,
            actor_display=actor.display_name,
        )


async def finalize_operation(factory, current: LogSnapshot, request, permission: str, action: str, metadata: dict[str, object]) -> None:
    async with factory() as session:
        actor = await session.get(User, current.actor_id, populate_existing=True)
        item = await session.get(LogDataSource, current.identifier, populate_existing=True)
        rejection = None
        if actor is None or not actor.is_active or not await user_has_permissions(session, actor, (permission,)):
            rejection = (403, "账号或日志权限已变化。", "authorization_changed")
        elif item is None or not item.is_enabled or log_fingerprint(persisted_state(item)) != current.fingerprint:
            rejection = (409, "日志数据源配置已变化或被删除，请重新查询。", "configuration_changed")
        event_actor = actor or SimpleNamespace(username=current.actor_username, display_name=current.actor_display)
        event_metadata = dict(metadata)
        if rejection is not None:
            event_metadata.update(result="rejected", failure_category=rejection[2])
        await record_event(
            session,
            actor=event_actor,
            method=request.method,
            path=request.url.path,
            ip_address=request.client.host if request.client else "",
            correlation_id=getattr(request.state, "correlation_id", ""),
            action=action,
            title="日志数据源运行",
            resource_type="log_datasource",
            resource_id=str(current.identifier),
            metadata=event_metadata,
            module="ops",
            category="log",
        )
        await session.commit()
        if rejection is not None:
            raise HTTPException(rejection[0], rejection[1])


def target(config):
    try:
        return validate_origin(str(config.get("endpoint", "")), allowed_origins())
    except (ValueError, UnicodeError):
        raise HTTPException(400, "日志服务地址无效或未获服务端授权。") from None


def elk_source_allowed(source: str, configured: str) -> bool:
    try:
        included, excluded = parse_elk_index_pattern(configured)
    except ValueError:
        return False
    if source == configured:
        return True
    if not source or source in {"*", "_all"} or any(char in source for char in "*?[],:\x00"):
        return False
    matches = lambda pattern: re.fullmatch(re.escape(pattern).replace(r"\*", ".*"), source) is not None
    return any(matches(pattern) for pattern in included) and not any(matches(pattern) for pattern in excluded)


def remote_failure_category(exc: HTTPException) -> str:
    if exc.status_code == 504:
        return "timeout"
    return "admission" if exc.status_code == 400 else "remote_or_protocol"


def elk_headers(config):
    kind = config.get("auth_type", "none")
    if kind == "basic":
        token = base64.b64encode(f"{config.get('username','')}:{config.get('password','')}".encode()).decode()
        return {"Authorization": f"Basic {token}"}
    if kind == "api_key":
        return {"Authorization": f"ApiKey {config.get('api_key','')}"}
    if kind == "bearer":
        return {"Authorization": f"Bearer {config.get('bearer_token','')}"}
    return {}


async def catalog(factory, actor_id, provider, request, body):
    current = await snapshot(factory, body.datasource_id, actor_id, "ops.log.query")
    started = time.perf_counter()
    base = {"provider": current.provider, "catalog_action": body.action}
    try:
        result = await _catalog(current, provider, body)
    except LogAddressError:
        await finalize_operation(factory, current, request, "ops.log.query", "catalog_logs", {**base, "duration_ms": int((time.perf_counter() - started) * 1000), "result": "failed", "failure_category": "address_rejected"})
        raise HTTPException(400, "日志服务地址解析到未获授权的网络。") from None
    except HTTPException as exc:
        await finalize_operation(factory, current, request, "ops.log.query", "catalog_logs", {**base, "duration_ms": int((time.perf_counter() - started) * 1000), "result": "failed", "failure_category": remote_failure_category(exc)})
        raise
    except TimeoutError:
        await finalize_operation(factory, current, request, "ops.log.query", "catalog_logs", {**base, "duration_ms": int((time.perf_counter() - started) * 1000), "result": "failed", "failure_category": "timeout"})
        raise HTTPException(504, "日志服务请求超时，请稍后重试。") from None
    except ValueError:
        await finalize_operation(factory, current, request, "ops.log.query", "catalog_logs", {**base, "duration_ms": int((time.perf_counter() - started) * 1000), "result": "failed", "failure_category": "remote_or_protocol"})
        raise HTTPException(502, "日志服务请求失败，请检查数据源配置。") from None
    await finalize_operation(factory, current, request, "ops.log.query", "catalog_logs", {**base, "duration_ms": int((time.perf_counter() - started) * 1000), "result": "success", "item_count": result["count"]})
    return result


async def _catalog(current, provider, body):
    config = current.config
    if current.provider != provider:
        raise HTTPException(400, "数据源类型与请求路径不一致。")
    if provider == "loki":
        if body.action == "labels":
            suffix = "/loki/api/v1/labels"
        elif body.action == "label_values":
            suffix = f"/loki/api/v1/label/{quote(body.label, safe='')}/values"
        else:
            raise HTTPException(400, "Loki 目录操作无效。")
        params = {}
        if body.start_ms is not None:
            params["start"] = body.start_ms * 1_000_000
        if body.end_ms is not None:
            params["end"] = body.end_ms * 1_000_000
        result = await request_json(target(config), "GET", suffix, params=params)
        items = sorted(set(result.get("data", [])))[:1000]
    elif provider == "elk":
        if body.action != "sources":
            raise HTTPException(400, "Elasticsearch 仅支持读取索引目录。")
        pattern = body.index_pattern or config.get("index_pattern", "logs-*")
        if not elk_source_allowed(pattern, config.get("index_pattern", "logs-*")):
            raise HTTPException(400, "Elasticsearch 索引范围必须与数据源配置一致。")
        result = await request_json(target(config), "GET", "/_resolve/index/" + quote(pattern, safe="*,-_"), headers=elk_headers(config))
        names = [row.get("name") for key in ("indices", "aliases", "data_streams") for row in result.get(key, [])]
        items = sorted({name for name in names if name})[:1000]
    else:
        if body.action != "sources":
            raise HTTPException(400, "SLS 仅支持读取日志库目录。")
        from ops.observability.logs.providers.sls import list_logstores
        available = await list_logstores(config)
        configured = config.get("logstore", "")
        items = [configured] if configured in available else []
    projected = items if provider == "loki" else [{"name": item} for item in items]
    return {"provider": provider, "items": projected, "count": len(items)}


async def query(factory, actor_id, request, body):
    current = await snapshot(factory, body.datasource_id, actor_id, "ops.log.query")
    started = time.perf_counter()
    base = {"provider": current.provider, "query_length": len(body.query), "limit": body.limit}
    try:
        result = await _query(current, body)
    except LogAddressError:
        await finalize_operation(factory, current, request, "ops.log.query", "query_logs", {**base, "duration_ms": int((time.perf_counter() - started) * 1000), "result": "failed", "failure_category": "address_rejected"})
        raise HTTPException(400, "日志服务地址解析到未获授权的网络。") from None
    except HTTPException as exc:
        await finalize_operation(factory, current, request, "ops.log.query", "query_logs", {**base, "duration_ms": int((time.perf_counter() - started) * 1000), "result": "failed", "failure_category": remote_failure_category(exc)})
        raise
    except TimeoutError:
        await finalize_operation(factory, current, request, "ops.log.query", "query_logs", {**base, "duration_ms": int((time.perf_counter() - started) * 1000), "result": "failed", "failure_category": "timeout"})
        raise HTTPException(504, "日志服务请求超时，请稍后重试。") from None
    except ValueError:
        await finalize_operation(factory, current, request, "ops.log.query", "query_logs", {**base, "duration_ms": int((time.perf_counter() - started) * 1000), "result": "failed", "failure_category": "remote_or_protocol"})
        raise HTTPException(502, "日志服务请求失败，请检查数据源配置。") from None
    await finalize_operation(factory, current, request, "ops.log.query", "query_logs", {**base, "duration_ms": int((time.perf_counter() - started) * 1000), "result": "success", "result_count": len(result["logs"])})
    return result


async def _query(current, body):
    provider, config, public = current.provider, current.config, current.public
    if provider != body.provider:
        raise HTTPException(400, "数据源类型与查询类型不一致。")
    if provider == "loki":
        result = await request_json(target(config), "GET", "/loki/api/v1/query_range", params={"query": body.query, "start": body.start_ms * 1_000_000, "end": body.end_ms * 1_000_000, "limit": body.limit, "direction": "backward"})
        logs = parse_query(result)[:body.limit]
        total, took, progress = len(logs), None, "Complete"
    elif provider == "elk":
        source = body.source or body.index_pattern or config.get("index_pattern", "logs-*")
        if not elk_source_allowed(source, config.get("index_pattern", "logs-*")):
            raise HTTPException(400, "Elasticsearch 索引范围必须与数据源配置一致。")
        result = await request_json(target(config), "POST", "/" + quote(source, safe="*,-_") + "/_search", headers=elk_headers(config), body=build_search_body(body.query, body.start_ms, body.end_ms, body.limit, body.time_field or config.get("time_field", "@timestamp")))
        logs, total, took = parse_search(result, [item.strip() for item in (body.message_fields or config.get("message_fields", "message,log,msg")).split(",")])
        progress = "Complete"
    else:
        from ops.observability.logs.providers.sls import query_logs
        requested_logstore = body.logstore or body.source or config.get("logstore", "")
        if requested_logstore != config.get("logstore", ""):
            raise HTTPException(400, "SLS 日志库必须与数据源配置一致。")
        logs, total, took, progress = await query_logs(config, body)
    return {"provider": provider, "source": public["name"], "total": total, "took_ms": took, "progress": progress, "logs": logs}


async def test_connection(factory, actor_id, request, identifier):
    current = await snapshot(factory, identifier, actor_id, "ops.log.datasource.manage")
    started = time.perf_counter()
    base = {"provider": current.provider}
    try:
        result = await _test_connection(current)
    except LogAddressError:
        await finalize_operation(factory, current, request, "ops.log.datasource.manage", "test_log_datasource", {**base, "duration_ms": int((time.perf_counter() - started) * 1000), "result": "failed", "failure_category": "address_rejected"})
        raise HTTPException(400, "日志服务地址解析到未获授权的网络。") from None
    except HTTPException as exc:
        await finalize_operation(factory, current, request, "ops.log.datasource.manage", "test_log_datasource", {**base, "duration_ms": int((time.perf_counter() - started) * 1000), "result": "failed", "failure_category": remote_failure_category(exc)})
        raise
    except TimeoutError:
        await finalize_operation(factory, current, request, "ops.log.datasource.manage", "test_log_datasource", {**base, "duration_ms": int((time.perf_counter() - started) * 1000), "result": "failed", "failure_category": "timeout"})
        raise HTTPException(504, "日志服务请求超时，请稍后重试。") from None
    except ValueError:
        await finalize_operation(factory, current, request, "ops.log.datasource.manage", "test_log_datasource", {**base, "duration_ms": int((time.perf_counter() - started) * 1000), "result": "failed", "failure_category": "remote_or_protocol"})
        raise HTTPException(502, "日志服务请求失败，请检查数据源配置。") from None
    await finalize_operation(factory, current, request, "ops.log.datasource.manage", "test_log_datasource", {**base, "duration_ms": int((time.perf_counter() - started) * 1000), "result": "success", "preview_count": result["preview_count"]})
    return result


async def _test_connection(current):
    provider, config = current.provider, current.config
    if provider == "loki":
        result = await request_json(target(config), "GET", "/loki/api/v1/query_range", params={"query": '{job=~".+"}', "start": 0, "end": int(datetime.now(timezone.utc).timestamp()*1e9), "limit": 1, "direction": "backward"})
        count = len(parse_query(result))
    elif provider == "elk":
        result = await request_json(target(config), "GET", "/_resolve/index/" + quote(config.get("index_pattern", "logs-*"), safe="*,-_"), headers=elk_headers(config))
        count = sum(len(result.get(key, [])) for key in ("indices", "aliases", "data_streams"))
    else:
        from ops.observability.logs.providers.sls import list_logstores
        count = len(await list_logstores(config))
    return {"success": True, "message": "连接测试成功", "preview_count": count}
