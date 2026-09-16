from sqlalchemy.ext.asyncio import AsyncSession

from aidevops.sanitization import is_sensitive_key, sanitize_metadata
from eventwall.models import EventRecord
from rbac.models import User


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
    category: str = 'system',
    severity: str = 'info',
    module: str = 'rbac',
) -> EventRecord:
    event = EventRecord(
        module=module,
        category=category,
        severity=severity,
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
