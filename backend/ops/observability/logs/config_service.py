from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import update

from aidevops.config_secrets import ENVELOPE, encrypt_secret
from eventwall.services import record_event
from ops.models import LogDataSource
from ops.observability.logs.selectors import get_data_source


SECRET_FIELDS = {"elk": {"password", "api_key", "bearer_token"}, "sls": {"access_key_id", "access_key_secret"}, "loki": set()}
MARKERS = {"", "configured", "***"}


def mask_config(provider, config):
    output = deepcopy(config)
    for key in SECRET_FIELDS.get(provider, set()):
        if output.get(key):
            output[key] = "configured"
    return output


def protect_config(provider, submitted, current=None):
    current = current if isinstance(current, dict) else {}
    output = deepcopy(submitted)
    active = SECRET_FIELDS.get(provider, set())
    if provider == "elk":
        active = {"basic": "password", "api_key": "api_key", "bearer": "bearer_token"}.get(output.get("auth_type", "none"), "")
        active = {active} if active else set()
    for key in SECRET_FIELDS.get(provider, set()):
        if key not in active:
            output.pop(key, None)
            continue
        value = output.get(key, "")
        if not isinstance(value, str):
            raise HTTPException(422, "日志数据源凭据必须是字符串。")
        if isinstance(value, str) and not value.strip():
            value = ""
        if value in MARKERS:
            existing = current.get(key)
            if isinstance(existing, dict) and ENVELOPE in existing:
                output[key] = deepcopy(existing)
            elif isinstance(existing, str) and existing:
                output[key] = {ENVELOPE: encrypt_secret(existing)}
            else:
                raise HTTPException(422, "日志数据源缺少必要认证凭据。")
        else:
            output[key] = {ENVELOPE: encrypt_secret(value)}
    return output


async def audit(session, request, actor, action, item):
    await record_event(session, actor=actor, method=request.method, path=request.url.path, ip_address=request.client.host if request.client else "", correlation_id=getattr(request.state, "correlation_id", ""), action=action, title="日志数据源管理", resource_type="log_datasource", resource_id=str(item.id), metadata={"provider": item.provider}, module="ops", category="log")


async def save_data_source(session, request, actor, values, identifier=None):
    item = await get_data_source(session, identifier, lock=True) if identifier else LogDataSource()
    old_config = item.config if identifier and item.provider == values["provider"] else {}
    for field in ("name", "provider", "description", "is_enabled", "is_default"):
        setattr(item, field, values[field])
    item.config = protect_config(item.provider, values["config"], old_config)
    if not identifier:
        session.add(item)
        await session.flush()
    if item.is_default:
        await session.execute(update(LogDataSource).where(LogDataSource.provider == item.provider, LogDataSource.id != item.id).values(is_default=False))
    await session.flush()
    await audit(session, request, actor, "create_log_datasource" if identifier is None else "update_log_datasource", item)
    return item


async def remove_data_source(session, request, actor, identifier):
    item = await get_data_source(session, identifier, lock=True)
    await session.delete(item)
    await session.flush()
    await audit(session, request, actor, "delete_log_datasource", item)
