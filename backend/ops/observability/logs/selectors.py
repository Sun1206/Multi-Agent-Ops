from fastapi import HTTPException
from sqlalchemy import select

from ops.models import LogDataSource


PROVIDER_LABELS = {"loki": "Loki", "elk": "ELK / Elasticsearch", "sls": "阿里云 SLS"}


def filtered_data_sources(params):
    statement = select(LogDataSource)
    if params.get("provider"):
        statement = statement.where(LogDataSource.provider == params["provider"])
    if params.get("is_enabled") not in (None, ""):
        raw = str(params["is_enabled"]).lower()
        if raw not in {"true", "false", "1", "0"}:
            raise HTTPException(422, "is_enabled 筛选值无效。")
        statement = statement.where(LogDataSource.is_enabled.is_(raw in {"true", "1"}))
    return statement.order_by(LogDataSource.is_default.desc(), LogDataSource.name, LogDataSource.id)


async def get_data_source(session, identifier, *, lock=False):
    statement = select(LogDataSource).where(LogDataSource.id == identifier).execution_options(populate_existing=True)
    if lock:
        statement = statement.with_for_update()
    item = await session.scalar(statement)
    if item is None:
        raise HTTPException(404, "日志数据源不存在。")
    return item


def project_data_source(item, *, include_config=True):
    from ops.observability.logs.config_service import mask_config
    result = {name: getattr(item, name) for name in ("id", "name", "provider", "description", "is_enabled", "is_default")}
    result["provider_display"] = PROVIDER_LABELS.get(item.provider, item.provider)
    if include_config:
        result.update(config=mask_config(item.provider, item.config if isinstance(item.config, dict) else {}), created_at=item.created_at, updated_at=item.updated_at)
    return result
