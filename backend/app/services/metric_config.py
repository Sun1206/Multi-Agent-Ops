# 原子维护指标数据源、兼容配置密文、默认项互斥和安全操作审计。

from copy import deepcopy
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select

from app.core.exceptions import BusinessError
from app.models import MetricDataSource
from app.models.rbac import utc_now
from app.selectors.metrics import get_data_source
from app.services.config_secrets import ENVELOPE, encrypt_secret
from app.services.events import is_sensitive_key, record_event


WRITABLE_FIELDS = frozenset(
    {
        "name",
        "provider",
        "description",
        "environment",
        "cluster_name",
        "tsdb_type",
        "config",
        "is_enabled",
        "is_default",
    }
)
SECRET_MARKERS = frozenset({"***", "configured"})


# 只有字符串形式的页面占位符才是掩码，密文 envelope 不是集合成员。
def is_secret_marker(value) -> bool:
    return isinstance(value, str) and value in SECRET_MARKERS


# 读取同一语义的兼容字段，发生两个不同正式值时拒绝模糊配置。
def compatible_value(config, first, second, default=None):
    one = config.get(first)
    two = config.get(second)
    if one in (None, ""):
        return two if two is not None else default
    if two in (None, ""):
        return one
    if one != two:
        raise BusinessError(f"兼容配置字段 {first} 与 {second} 不一致。")
    return one


# 从 Basic 兼容对象中读取账号或密码字段。
def basic_value(config, key):
    basic = config.get("prometheus.basic")
    return basic.get(key) if isinstance(basic, dict) else None


# 解读掩码、清空和新秘密，旧明文在首次写操作时自动升级成密文。
def protect_secret(value, old=None, *, trusted=False):
    if isinstance(value, dict):
        if trusted and set(value) == {ENVELOPE} and isinstance(value[ENVELOPE], str):
            return deepcopy(value)
        if ENVELOPE in value:
            raise BusinessError("客户端不能提交凭据密文封装。")
        raise BusinessError("指标数据源敏感字段必须是字符串。")
    if not isinstance(value, str):
        raise BusinessError("指标数据源敏感字段必须是字符串。")
    if is_secret_marker(value):
        if old in (None, ""):
            raise BusinessError("新凭据路径不能使用掩码。")
        if isinstance(old, dict) and ENVELOPE in old:
            return deepcopy(old)
        if not isinstance(old, str):
            raise BusinessError("已有凭据格式无效。")
        return {ENVELOPE: encrypt_secret(old)}
    return {ENVELOPE: encrypt_secret(value)} if value else ""


# 在同一秘密的页面兼容路径中选择旋转、保留或清空值。
def submitted_secret(config, first, second, old_config, *, trusted=False):
    first_present = first in config
    second_present = second is not None and isinstance(config.get("prometheus.basic"), dict) and second in config["prometheus.basic"]
    first_value = config.get(first) if first_present else None
    second_value = basic_value(config, second) if second_present else None
    candidates = [value for value, present in ((first_value, first_present), (second_value, second_present)) if present]
    concrete = [value for value in candidates if not is_secret_marker(value)]
    if len(concrete) > 1 and concrete[0] != concrete[1]:
        raise BusinessError("兼容凭据字段提交了不同值。")
    if concrete:
        chosen = concrete[0]
    elif candidates:
        chosen = candidates[0]
    old = old_config.get(first)
    if old in (None, "") and second is not None:
        old = basic_value(old_config, second)
    if not candidates:
        chosen = "***" if old not in (None, "") else ""
    return protect_secret(chosen, old, trusted=trusted)


# 对 headers 的每个值独立加密，并允许页面掩码保留同名旧值。
def protect_headers(value, old=None, *, trusted=False):
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise BusinessError("指标请求 headers 必须是对象。")
    previous = old if isinstance(old, dict) else {}
    return {name: protect_secret(raw, previous.get(name), trusted=trusted) for name, raw in value.items()}


# 将页面的重复兼容键归一为稳定结构，并加密所有秘密叶子。
def normalize_metric_config(
    value: dict[str, object],
    old: dict[str, object] | None = None,
    *,
    trusted: bool = False,
    merge_old: bool = False,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise BusinessError("指标数据源 config 必须是对象。")
    old = old if isinstance(old, dict) else {}
    output = deepcopy(old) if merge_old else {}
    output.update(deepcopy(value))
    query_url = compatible_value(value, "query_url", "prometheus.addr", compatible_value(old, "query_url", "prometheus.addr", ""))
    timeout = compatible_value(value, "timeout", "prometheus.timeout", compatible_value(old, "timeout", "prometheus.timeout", 6))
    username = value.get("username", basic_value(value, "prometheus.user"))
    if username in (None, ""):
        username = old.get("username", basic_value(old, "prometheus.user") or "")
    password = submitted_secret(value, "password", "prometheus.password", old, trusted=trusted)
    old_bearer = old.get("bearer_token")
    bearer_value = value["bearer_token"] if "bearer_token" in value else ("***" if old_bearer not in (None, "") else "")
    bearer = protect_secret(bearer_value, old_bearer, trusted=trusted)
    raw_headers = compatible_value(value, "headers", "prometheus.headers", compatible_value(old, "headers", "prometheus.headers", {}))
    old_headers = compatible_value(old, "headers", "prometheus.headers", {})
    headers_submitted = "headers" in value or "prometheus.headers" in value
    headers = protect_headers(raw_headers, old_headers, trusted=trusted or not headers_submitted)
    output.update(
        {
            "query_url": query_url or "",
            "prometheus.addr": query_url or "",
            "auth_type": value.get("auth_type", old.get("auth_type", "none")),
            "username": username or "",
            "password": password,
            "bearer_token": bearer,
            "headers": headers,
            "prometheus.headers": deepcopy(headers),
            "timeout": timeout,
            "prometheus.timeout": timeout,
            "tls_skip_verify": value.get("tls_skip_verify", old.get("tls_skip_verify", False)),
            "prometheus.basic": {
                "prometheus.user": username or "",
                "prometheus.password": deepcopy(password),
            },
        }
    )
    return output


# 将所有敏感叶子替换为统一掩码，不需要解密也不会原地修改 ORM JSON。
def mask_metric_value(value, *, key="", inside_headers=False):
    sensitive = inside_headers or is_sensitive_key(key)
    if sensitive:
        return "***" if value not in (None, "", [], {}) else ""
    if isinstance(value, dict):
        if ENVELOPE in value:
            return "***"
        header_container = key.lower() in {"headers", "prometheus.headers"}
        return {
            child: mask_metric_value(item, key=str(child), inside_headers=header_container)
            for child, item in value.items()
        }
    if isinstance(value, list):
        return [mask_metric_value(item) for item in value]
    return deepcopy(value)


# 递归脱敏正式字段和旧配置中的未知嵌套敏感键，读取过程不修改数据库。
def mask_metric_config(value: dict[str, object]) -> dict[str, object]:
    return mask_metric_value(value)


# 写入只记录变更字段名的安全审计，绝不序列化 config 内容。
async def audit_metric_config(session, request, actor, action, identifier, fields):
    await record_event(
        session,
        actor=actor,
        method=request.method,
        path=request.url.path,
        ip_address=request.client.host if request.client else "",
        correlation_id=getattr(request.state, "correlation_id", ""),
        action=action,
        title="指标数据源管理",
        resource_type="metric_datasource",
        resource_id=str(identifier),
        metadata={"fields": sorted(fields)},
        module="ops",
        category="configuration",
    )


# 创建或更新数据源；默认项调整、秘密升级和审计共享调用方的一次事务提交。
async def save_data_source(
    session,
    request,
    actor,
    values,
    identifier: int | None = None,
    *,
    partial: bool = False,
) -> MetricDataSource:
    submitted = {key: deepcopy(item) for key, item in values.items() if key in WRITABLE_FIELDS}
    if identifier is None:
        item = MetricDataSource()
        session.add(item)
        current = {}
        action = "create_metric_datasource"
    else:
        item = await get_data_source(session, identifier, lock=True)
        current = {field: deepcopy(getattr(item, field)) for field in WRITABLE_FIELDS}
        previous_updated_at = item.updated_at
        action = "update_metric_datasource"
    final = {**current, **submitted}
    raw_config = final.get("config") if "config" in submitted else current.get("config", {})
    old_config = current.get("config", {})
    final["config"] = normalize_metric_config(
        raw_config or {},
        old_config if "config" in submitted else {},
        trusted="config" not in submitted,
        merge_old=partial and "config" in submitted,
    )
    for field in WRITABLE_FIELDS:
        if field in final:
            setattr(item, field, final[field])
    if identifier is not None:
        item.updated_at = max(utc_now(), previous_updated_at + timedelta(seconds=1))
    await session.flush()
    if item.is_default:
        others = list(
            (
                await session.scalars(
                    select(MetricDataSource)
                    .where(MetricDataSource.environment == item.environment, MetricDataSource.id != item.id)
                    .with_for_update()
                )
            ).all()
        )
        for other in others:
            other.is_default = False
    await audit_metric_config(session, request, actor, action, item.id, submitted)
    return item


# 删除明确指定的数据源并在同一事务保存删除审计。
async def remove_data_source(session, request, actor, identifier: int) -> None:
    item = await get_data_source(session, identifier, lock=True)
    await audit_metric_config(session, request, actor, "delete_metric_datasource", item.id, ())
    await session.delete(item)
