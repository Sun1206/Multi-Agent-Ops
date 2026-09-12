from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EventRecord, User


SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "accesskey",
    "privatekey",
    "certificate",
    "certcontent",
    "keycontent",
    "apikey",
    "sshcredential",
    "kubeconfig",
}


def normalize_key(key: object) -> str:
    """统一敏感字段名格式，忽略大小写、横线和下划线。"""
    return str(key).lower().replace("-", "").replace("_", "")


def is_sensitive_key(key: object) -> bool:
    """判断字段名是否包含需要完整遮蔽的凭据语义。"""
    normalized = normalize_key(key)
    return any(item in normalized for item in SENSITIVE_KEYS)


def sanitize_metadata(value: Any) -> Any:
    """递归清洗审计元数据中的密码、令牌、证书和访问凭据。"""
    if isinstance(value, Mapping):
        return {
            key: "***" if is_sensitive_key(key) else sanitize_metadata(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_metadata(item) for item in value]
    return value


async def record_event(
    session: AsyncSession,
    *,
    actor: User,
    method: str,
    path: str,
    ip_address: str,
    correlation_id: str,
    action: str,
    title: str,
    resource_type: str,
    resource_id: str,
    metadata: dict[str, object],
) -> EventRecord:
    """把已脱敏审计事件加入调用方事务；失败时业务写入应一并回滚。"""
    event = EventRecord(
        module="rbac",
        category="system",
        action=action,
        title=title,
        actor_username=actor.username,
        actor_display=actor.display_name,
        request_method=method,
        source_path=path,
        ip_address=ip_address,
        correlation_id=correlation_id,
        resource_type=resource_type,
        resource_id=resource_id,
        event_metadata=sanitize_metadata(metadata),
    )
    session.add(event)
    await session.flush()
    return event
